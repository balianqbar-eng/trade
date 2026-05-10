import re
import sqlite3
import shutil
import subprocess
import tempfile
import os
from hashlib import pbkdf2_hmac
from pathlib import Path

import requests

APP_ID = "nschool"
BASE_URL = "https://nschool.tw"
GRAPHQL_URL = "https://phdb.kolable.com/v1/graphql"

_CONTENT_QUERY = """
query GetProgramContent($contentId: uuid!) {
  program_content_by_pk(id: $contentId) {
    id
    title
    duration
    program_content_videos {
      attachment_id
    }
  }
}
"""


def _get_chrome_cookies() -> dict:
    try:
        from Crypto.Cipher import AES
    except ImportError:
        return {}

    try:
        key_password = subprocess.run(
            ['security', 'find-generic-password', '-a', 'Chrome', '-s', 'Chrome Safe Storage', '-w'],
            capture_output=True, text=True, timeout=5,
        ).stdout.strip().encode()
        if not key_password:
            return {}
    except Exception:
        return {}

    key = pbkdf2_hmac('sha1', key_password, b'saltysalt', 1003, dklen=16)

    def _decrypt(encrypted: bytes) -> str:
        if not encrypted or encrypted[:3] != b'v10':
            return encrypted.decode('utf-8', errors='replace') if encrypted else ''
        iv = b' ' * 16
        plaintext = AES.new(key, AES.MODE_CBC, iv).decrypt(encrypted[3:])
        pad = plaintext[-1]
        plaintext = plaintext[:-pad]
        return plaintext[32:].decode('utf-8', errors='replace')

    db_path = os.path.expanduser('~/Library/Application Support/Google/Chrome/Default/Cookies')
    if not os.path.exists(db_path):
        return {}

    try:
        with tempfile.NamedTemporaryFile(suffix='.db', delete=False) as f:
            tmp = f.name
        shutil.copy2(db_path, tmp)
        con = sqlite3.connect(tmp)
        rows = con.execute(
            "SELECT name, encrypted_value FROM cookies WHERE host_key LIKE '%nschool%'"
        ).fetchall()
        con.close()
        os.unlink(tmp)
        return {name: _decrypt(enc) for name, enc in rows}
    except Exception:
        return {}


def _get_auth_token() -> str:
    cookies = _get_chrome_cookies()
    session = requests.Session()
    session.cookies.update(cookies)

    resp = session.post(
        f"{BASE_URL}/api/v1/auth/refresh-token",
        json={"appId": APP_ID},
        timeout=10,
    )
    data = resp.json()
    code = data.get("code")
    if code != "SUCCESS":
        if code == "E_NO_MEMBER" or not cookies:
            raise RuntimeError(
                "nschool.tw 未登入：請先在 Chrome 瀏覽器中登入 nschool.tw，再重試。"
            )
        raise RuntimeError(f"nschool.tw 認證失敗：{data.get('message', code)}")
    return data["result"]["authToken"]


def _get_content_video_id(content_id: str, token: str) -> tuple[str, str, int | None]:
    resp = requests.post(
        GRAPHQL_URL,
        json={"query": _CONTENT_QUERY, "variables": {"contentId": content_id}},
        headers={
            "Authorization": f"Bearer {token}",
            "x-hasura-app-id": APP_ID,
        },
        timeout=10,
    )
    data = resp.json()
    content = (data.get("data") or {}).get("program_content_by_pk")
    if not content:
        raise RuntimeError(f"找不到課程內容 {content_id}，請確認已購買此課程。")

    videos = content.get("program_content_videos") or []
    if not videos:
        raise RuntimeError(f"此內容沒有影片：{content.get('title')}")

    video_id = videos[0]["attachment_id"]
    title = content.get("title", content_id)
    duration = content.get("duration")
    return video_id, title, duration


def _get_hls_url(video_id: str, token: str) -> str:
    resp = requests.get(
        f"{BASE_URL}/api/v2/videos/{video_id}/sign",
        headers={"Authorization": f"Bearer {token}"},
        timeout=10,
    )
    data = resp.json()
    if not data.get("result"):
        raise RuntimeError(f"無法取得影片簽名 URL：{data}")

    paths = data["result"]["videoSignedPaths"]
    hls_path = paths.get("hlsPath") or paths.get("cloudfrontMigratedHlsPath")
    if not hls_path:
        raise RuntimeError(f"找不到 HLS path：{paths}")

    return f"https://media.kolable.com{hls_path}"


def _ffmpeg_download_hls(master_url: str, output_path: Path) -> None:
    """Download HLS stream. Rewrites m3u8 with full signed segment URLs so ffmpeg works."""
    from urllib.parse import urlparse

    qs = urlparse(master_url).query
    master_base = master_url.rsplit("/", 1)[0].split("?")[0]

    # Fetch master playlist and pick highest-bandwidth stream
    resp = requests.get(master_url, timeout=10)
    resp.raise_for_status()
    lines = resp.text.splitlines()

    best_path = None
    best_bw = 0
    for i, line in enumerate(lines):
        if line.startswith("#EXT-X-STREAM-INF"):
            attrs = line.split(":", 1)[1] if ":" in line else line
            bw = 0
            for part in attrs.split(","):
                if part.startswith("BANDWIDTH="):
                    bw = int(part.split("=")[1])
            if bw > best_bw and i + 1 < len(lines):
                best_bw = bw
                best_path = lines[i + 1].strip()

    if not best_path:
        raise RuntimeError("無法從 m3u8 master playlist 找到可用串流")

    # Fetch sub-playlist
    sub_url = (best_path if best_path.startswith("http") else f"{master_base}/{best_path}")
    sub_url_signed = f"{sub_url}?{qs}" if "?" not in sub_url else sub_url
    sub_base = sub_url.rsplit("/", 1)[0]

    r2 = requests.get(sub_url_signed, timeout=10)
    r2.raise_for_status()

    # Rewrite segment URLs to include CloudFront signature
    new_lines = []
    for line in r2.text.splitlines():
        stripped = line.strip()
        if stripped and not stripped.startswith("#"):
            full = stripped if stripped.startswith("http") else f"{sub_base}/{stripped}"
            full_signed = f"{full}?{qs}" if "?" not in full else full
            new_lines.append(full_signed)
        else:
            new_lines.append(line)

    # Write rewritten playlist to temp file
    tmp_m3u8 = output_path.with_suffix(".tmp.m3u8")
    tmp_m3u8.write_text("\n".join(new_lines))

    try:
        result = subprocess.run(
            [
                "ffmpeg", "-y",
                "-allowed_extensions", "ALL",
                "-protocol_whitelist", "file,crypto,data,http,https,tcp,tls",
                "-i", str(tmp_m3u8),
                "-c", "copy",
                str(output_path),
            ],
            capture_output=True,
            text=True,
        )
    finally:
        tmp_m3u8.unlink(missing_ok=True)

    if result.returncode != 0:
        raise RuntimeError(f"ffmpeg 下載失敗：{result.stderr[-800:]}")


def download(url: str, output_dir: Path) -> dict:
    match = re.search(r"/programs/([^/]+)/contents/([^/?#]+)", url)
    if not match:
        raise ValueError(f"無效的 nschool.tw URL：{url}")
    content_id = match.group(2)

    token = _get_auth_token()
    video_id, title, duration = _get_content_video_id(content_id, token)
    hls_url = _get_hls_url(video_id, token)

    output_path = output_dir / f"{content_id}.mp4"
    _ffmpeg_download_hls(hls_url, output_path)

    return {
        "video_path": output_path,
        "title": title,
        "duration": duration,
        "source_type": "url",
    }

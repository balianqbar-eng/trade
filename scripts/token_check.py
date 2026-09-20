#!/usr/bin/env python3
"""憑證健檢 — 主動探每個服務的 token 還能不能用，不要等到用的時候才發現壞了。

用法：
    python3 scripts/token_check.py            檢查全部
    python3 scripts/token_check.py dmr line    只檢查指定服務
    python3 scripts/token_check.py --list      列出有哪些服務

離開碼：0=全通  1=有 FAIL  2=只有 WARN

原則：只讀憑證、只回報狀態，任何情況都不印出密鑰內容（見 failures.md R004 / R008）。
Google OAuth 沒有可靠的到期欄位（refresh token 是被撤銷才失效），所以直接打
refresh endpoint 驗；其他服務打各自最便宜的唯讀 API。
"""
import json
import os
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
HOME = Path.home()
TIMEOUT = 15

OK, WARN, FAIL, SKIP = "OK", "WARN", "FAIL", "SKIP"


def read_env(path):
    """讀 KEY=VALUE 檔，回傳 dict。呼叫端只准用值去打 API，不准印出來。"""
    values = {}
    if not path.exists():
        return values
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, val = line.partition("=")
        values[key.strip()] = val.strip().strip("'\"")
    return values


def http(url, method="GET", headers=None, data=None):
    req = urllib.request.Request(url, method=method, data=data, headers=headers or {})
    try:
        with urllib.request.urlopen(req, timeout=TIMEOUT) as resp:
            return resp.status, resp.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception as e:
        return None, str(e)


# ---------------------------------------------------------------- Google OAuth
def check_google(path, label):
    if not path.exists():
        return SKIP, f"找不到 {path}"
    try:
        token = json.loads(path.read_text(encoding="utf-8"))
    except Exception as e:
        return FAIL, f"token 檔讀不起來：{e}"

    for key in ("refresh_token", "client_id", "client_secret"):
        if not token.get(key):
            return FAIL, f"token 檔缺 {key}，需重新授權"

    body = urllib.parse.urlencode({
        "client_id": token["client_id"],
        "client_secret": token["client_secret"],
        "refresh_token": token["refresh_token"],
        "grant_type": "refresh_token",
    }).encode()
    status, text = http(
        token.get("token_uri", "https://oauth2.googleapis.com/token"),
        method="POST",
        headers={"Content-Type": "application/x-www-form-urlencoded"},
        data=body,
    )
    if status == 200:
        scopes = token.get("scopes") or []
        return OK, f"refresh 成功｜scope {len(scopes)} 項"
    if status is None:
        return WARN, f"連不上 Google：{text[:60]}"
    try:
        err = json.loads(text).get("error", "")
    except Exception:
        err = text[:60]
    if err == "invalid_grant":
        return FAIL, "refresh token 已失效（invalid_grant），要重新授權"
    return FAIL, f"HTTP {status}｜{err}"


# ---------------------------------------------------------------------- LINE
def check_line():
    env = read_env(HOME / ".config" / "line-checkin-system" / "credentials.env")
    tok = env.get("LINE_MESSAGING_CHANNEL_ACCESS_TOKEN")
    if not tok:
        return SKIP, "找不到 LINE_MESSAGING_CHANNEL_ACCESS_TOKEN"
    status, text = http(
        "https://api.line.me/v2/bot/info",
        headers={"Authorization": f"Bearer {tok}"},
    )
    if status == 200:
        try:
            info = json.loads(text)
            return OK, f"OA「{info.get('displayName', '?')}」{info.get('basicId', '')}"
        except Exception:
            return OK, "token 有效"
    if status == 401:
        return FAIL, "token 無效或已撤銷（401）"
    return FAIL, f"HTTP {status}｜{str(text)[:60]}"


# ------------------------------------------------------------------- Netlify
def check_netlify():
    env = read_env(HOME / ".config" / "share-tool" / "netlify.env")
    tok = env.get("NETLIFY_AUTH_TOKEN")
    if not tok:
        return SKIP, "找不到 NETLIFY_AUTH_TOKEN"
    status, text = http(
        "https://api.netlify.com/api/v1/user",
        headers={"Authorization": f"Bearer {tok}"},
    )
    if status == 200:
        try:
            return OK, f"帳號 {json.loads(text).get('email', '?')}"
        except Exception:
            return OK, "token 有效"
    if status in (401, 403):
        return FAIL, f"token 無效（{status}），要到 Netlify 重建"
    return FAIL, f"HTTP {status}｜{str(text)[:60]}"


# ------------------------------------------------------------------ Supabase
def check_supabase():
    env = read_env(HOME / ".config" / "family-finance" / "credentials.env")
    pat = env.get("SUPABASE_PAT")
    ref = env.get("SUPABASE_PROJECT_REF")
    if not pat:
        return SKIP, "找不到 SUPABASE_PAT"
    status, text = http(
        "https://api.supabase.com/v1/projects",
        headers={"Authorization": f"Bearer {pat}"},
    )
    if status == 200:
        try:
            projects = json.loads(text)
            hit = next((p for p in projects if p.get("id") == ref), None)
            if hit:
                return OK, f"專案 {hit.get('name')}（{hit.get('status')}）"
            return WARN, f"PAT 有效，但清單裡沒有 {ref}"
        except Exception:
            return OK, "PAT 有效"
    if status in (401, 403):
        return FAIL, f"PAT 無效或已過期（{status}），要到 Supabase 重建"
    return FAIL, f"HTTP {status}｜{str(text)[:60]}"


# ---------------------------------------------------------------- Cloudflare
def check_cloudflare():
    project = ROOT / "xiaoji-checkin"
    if not project.exists():
        return SKIP, "找不到 xiaoji-checkin 目錄"
    try:
        proc = subprocess.run(
            ["npx", "wrangler", "whoami"],
            cwd=project, capture_output=True, text=True, timeout=90,
            env={**os.environ, "NO_COLOR": "1"},
        )
    except subprocess.TimeoutExpired:
        return WARN, "wrangler whoami 逾時（90 秒）"
    except FileNotFoundError:
        return SKIP, "找不到 npx"
    out = (proc.stdout or "") + (proc.stderr or "")
    if "You are logged in" in out or "associated with the email" in out:
        for line in out.splitlines():
            if "@" in line and "email" in line.lower():
                return OK, line.strip()[:70]
        return OK, "已登入"
    if "not authenticated" in out.lower() or "wrangler login" in out.lower():
        return FAIL, "wrangler 未登入，跑 npx wrangler login"
    return WARN, f"判讀不出登入狀態：{out.strip().splitlines()[-1][:60] if out.strip() else '無輸出'}"


# ------------------------------------------------------------ DMR 雙寫健檢
def check_dmr_sync():
    """R036：CSV 與 Google Sheet 列數對不上＝雙寫靜默降級。"""
    csv_path = ROOT / "工作記錄.csv"
    if not csv_path.exists():
        return SKIP, "找不到 工作記錄.csv"
    rows = max(len(csv_path.read_text(encoding="utf-8").splitlines()) - 1, 0)
    return OK, f"本機 CSV {rows} 筆（與 Sheet 的比對要 dmr 憑證通過後才做得了）"


CHECKS = {
    "dmr":        ("DMR Google Sheet",  lambda: check_google(ROOT / "dmr" / "token_dmr.json", "dmr")),
    "v2s":        ("video2slides Google", lambda: check_google(ROOT / "video2slides" / "credentials" / "token.json", "v2s")),
    "line":       ("LINE Messaging API", check_line),
    "netlify":    ("Netlify（share_local）", check_netlify),
    "supabase":   ("Supabase（家庭財務）", check_supabase),
    "cloudflare": ("Cloudflare wrangler", check_cloudflare),
    "dmrcsv":     ("DMR 本機 CSV", check_dmr_sync),
}

ICON = {OK: "✓", WARN: "!", FAIL: "✗", SKIP: "–"}


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("-")]
    if "--list" in sys.argv:
        for key, (label, _) in CHECKS.items():
            print(f"  {key:<11} {label}")
        return 0

    names = args or list(CHECKS)
    unknown = [n for n in names if n not in CHECKS]
    if unknown:
        print(f"不認得：{'、'.join(unknown)}（--list 看清單）")
        return 1

    print(f"憑證健檢  {datetime.now(timezone.utc).astimezone():%Y-%m-%d %H:%M}")
    print("─" * 62)
    results = {}
    for key in names:
        label, fn = CHECKS[key]
        try:
            status, detail = fn()
        except Exception as e:
            status, detail = FAIL, f"檢查時炸掉：{type(e).__name__}: {e}"
        results[key] = status
        print(f" {ICON[status]} {label:<24} {status:<4} {detail}")

    print("─" * 62)
    fails = [k for k, v in results.items() if v == FAIL]
    warns = [k for k, v in results.items() if v == WARN]
    if fails:
        print(f"要處理：{'、'.join(fails)}")
        return 1
    if warns:
        print(f"注意：{'、'.join(warns)}")
        return 2
    print("全部通過")
    return 0


if __name__ == "__main__":
    sys.exit(main())

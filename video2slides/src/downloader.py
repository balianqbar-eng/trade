import shutil
from pathlib import Path
from typing import Optional

import yt_dlp
from rich.progress import Progress, SpinnerColumn, TextColumn

from .config import settings


def download(video_input: str, output_dir: Optional[Path] = None) -> dict:
    out = output_dir or settings.output_dir
    out.mkdir(parents=True, exist_ok=True)

    if Path(video_input).exists():
        return _handle_local(Path(video_input), out)
    return _handle_url(video_input, out)


def _handle_local(path: Path, out: Path) -> dict:
    dest = out / path.name
    if dest != path:
        shutil.copy2(path, dest)
    return {
        "video_path": dest,
        "title": path.stem,
        "duration": None,
        "source_type": "local",
    }


def _handle_url(url: str, out: Path) -> dict:
    if "nschool.tw" in url:
        from .nschool import download as nschool_download
        return nschool_download(url, out)

    info: dict = {}

    def progress_hook(d):
        pass

    ydl_opts = {
        "format": "bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best",
        "outtmpl": str(out / "%(id)s.%(ext)s"),
        "merge_output_format": "mp4",
        "quiet": True,
        "no_warnings": True,
        "progress_hooks": [progress_hook],
    }

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
    ) as progress:
        progress.add_task("下載影片中...", total=None)
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            meta = ydl.extract_info(url, download=True)
            info = ydl.sanitize_info(meta)

    video_id = info.get("id", "video")
    video_path = out / f"{video_id}.mp4"

    return {
        "video_path": video_path,
        "title": info.get("title", video_id),
        "duration": info.get("duration"),
        "source_type": "url",
    }

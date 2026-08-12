import contextlib
import json
import shutil
import sys
import threading
import time
import uuid
import wave
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, HTMLResponse, RedirectResponse
from pydantic import BaseModel

sys.path.insert(0, str(Path(__file__).parent))

from src.audio_extractor import extract_audio
from src.config import settings
from src.content_analyzer import analyze
from src.downloader import download
from src.knowledge_exporter import export_knowledge
from src.scene_detector import detect_scenes
from src.slides_generator import _get_credentials, generate_slides
from src.transcriber import transcribe

from googleapiclient.discovery import build

app = FastAPI(title="video2slides bridge")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class JobRequest(BaseModel):
    url: str
    no_screenshots: bool = False
    language: str = "auto"
    video_type: str = ""


class ArchiveRequest(BaseModel):
    dest: str


class OrphanArchiveRequest(BaseModel):
    dest: str
    name: str


_STAGE_LABEL = {
    "queued": "排隊中",
    "downloading": "下載影片中",
    "extracting_audio": "抽取音訊中",
    "transcribing": "語音轉文字 + 場景偵測中",
    "analyzing": "AI 內容分析中",
    "generating_slides": "生成 Google Slides 中",
    "exporting": "匯出 PPTX / PDF 中",
    "completed": "已完成",
    "failed": "失敗",
}

_EXPORT_MIME = {
    "pptx": "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    "pdf": "application/pdf",
}

# 各階段預估秒數（僅作為 ETA 起始值；transcribing 會依音檔長度與實測速度覆寫）
_STAGE_ESTIMATE = {
    "downloading": 45,
    "extracting_audio": 8,
    "transcribing": 180,
    "analyzing": 25,
    "generating_slides": 20,
    "exporting": 12,
}

# 每秒音檔約需的轉錄秒數（mlx large-v3 / Apple Silicon 經驗值），僅在實測進度出現前使用
_TRANSCRIBE_RATE = 0.35

_TIMED_STAGES = list(_STAGE_ESTIMATE.keys())

JOBS_DIR = settings.output_dir / "jobs"
DOWNLOADS_DIR = settings.output_dir / "downloads"
META_DIR = JOBS_DIR / "_meta"

_jobs: dict[str, dict] = {}
_jobs_lock = threading.Lock()


def _persist_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        snap = {k: v for k, v in job.items() if not k.startswith("_")}
    META_DIR.mkdir(parents=True, exist_ok=True)
    (META_DIR / f"{job_id}.json").write_text(
        json.dumps(snap, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def _load_persisted_jobs():
    if not META_DIR.exists():
        return
    for f in META_DIR.glob("*.json"):
        try:
            data = json.loads(f.read_text(encoding="utf-8"))
            job_id = data.get("job_id")
            if not job_id:
                continue
            if data.get("status") == "running":
                data["status"] = "failed"
                data["stage"] = "failed"
                data["error"] = "server 重啟，原任務已中斷"
                data["message"] = "失敗：server 重啟導致中斷"
            _jobs[job_id] = data
        except Exception:
            continue


def _set_stage(job_id: str, stage: str, message: str | None = None):
    now = time.time()
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        prev = job.get("stage")
        prev_start = job.get("_stage_start")
        if prev and prev_start and prev in _TIMED_STAGES:
            elapsed = now - prev_start
            job.setdefault("stages_elapsed", {})[prev] = elapsed
        job["stage"] = stage
        job["message"] = message or _STAGE_LABEL.get(stage, stage)
        if stage != "transcribing":
            job.pop("progress", None)
        job["_stage_start"] = now
        if "started_at" not in job:
            job["started_at"] = now
    _persist_job(job_id)


def _resolve_job_dir(job: dict) -> Path | None:
    job_dir = job.get("job_dir")
    if not job_dir:
        return None
    p = Path(job_dir)
    return p if p.is_absolute() else Path(__file__).parent / p


def _dir_size(path: Path) -> int:
    return sum(f.stat().st_size for f in path.rglob("*") if f.is_file())


def _move_to_warehouse(src: Path, dest: str) -> dict:
    dest_root = Path(dest.strip()).expanduser()
    if not dest_root.is_absolute():
        raise HTTPException(400, "倉庫路徑必須是絕對路徑")
    if not dest_root.is_dir():
        raise HTTPException(400, f"倉庫路徑不存在或不是資料夾：{dest_root}")
    if dest_root.resolve() == src.resolve() or src.resolve() in dest_root.resolve().parents:
        raise HTTPException(400, "倉庫路徑不能在素材目錄內")

    target = dest_root / src.name
    if target.exists():
        raise HTTPException(409, f"目的地已有同名資料夾：{target}")

    size = _dir_size(src)
    shutil.move(str(src), str(target))
    return {"dest": str(target), "at": time.time(), "bytes": size}


def _jobs_root() -> Path:
    return JOBS_DIR if JOBS_DIR.is_absolute() else Path(__file__).parent / JOBS_DIR


def _orphan_dirs() -> list[Path]:
    root = _jobs_root()
    if not root.exists():
        return []
    with _jobs_lock:
        known = {
            str(d.resolve())
            for d in (_resolve_job_dir(j) for j in _jobs.values())
            if d is not None
        }
    return sorted(
        d for d in root.iterdir()
        if d.is_dir() and d.name != "_meta" and str(d.resolve()) not in known
    )


def _audio_duration(path: Path) -> float:
    with contextlib.closing(wave.open(str(path))) as w:
        return w.getnframes() / w.getframerate()


def _set_stage_estimate(job_id: str, stage: str, seconds: float):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        est = dict(job.get("_stage_estimate") or _STAGE_ESTIMATE)
        est[stage] = round(seconds)
        job["_stage_estimate"] = est


def _set_transcribe_progress(job_id: str, done_sec: float, total_sec: float):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            return
        job["progress"] = {
            "stage": "transcribing",
            "done": round(done_sec, 1),
            "total": round(total_sec, 1),
            "ratio": min(1.0, done_sec / total_sec) if total_sec else 0.0,
            "updated_at": time.time(),
        }


def _safe_filename(title: str, fallback: str) -> str:
    keep = " -_()[]．，。：（）、"
    cleaned = "".join(c for c in title if c.isalnum() or c in keep).strip()
    return cleaned or fallback


def _append_source_slide(outline: dict, video_url: str, video_title: str, video_id: str) -> dict:
    bullets = [f"原始影片：{video_url}"]
    if video_title:
        bullets.append(f"影片標題：{video_title}")
    bullets.append(f"處理時間：{datetime.now().strftime('%Y-%m-%d %H:%M')}")
    bullets.append(f"video_id：{video_id}")
    bullets.append("由 video2slides 自動產生")

    source_slide = {
        "type": "source",
        "title": "來源資訊",
        "subtitle": "可由此回溯原始影片",
        "bullets": bullets,
    }
    new_outline = dict(outline)
    new_outline["slides"] = list(outline.get("slides", [])) + [source_slide]
    return new_outline


def _run_job(job_id: str, url: str, opts: dict):
    try:
        _set_stage(job_id, "downloading")
        info = download(url, settings.output_dir)
        video_path = info["video_path"]
        video_id = video_path.stem

        job_dir = JOBS_DIR / video_id
        job_dir.mkdir(parents=True, exist_ok=True)
        new_video_path = job_dir / video_path.name
        if video_path.resolve() != new_video_path.resolve() and video_path.exists():
            shutil.move(str(video_path), str(new_video_path))
        video_path = new_video_path

        with _jobs_lock:
            _jobs[job_id]["title"] = info.get("title", "")
            _jobs[job_id]["job_dir"] = str(job_dir)

        _set_stage(job_id, "extracting_audio")
        audio_path = extract_audio(video_path, output_dir=job_dir)

        audio_sec = _audio_duration(audio_path)
        with _jobs_lock:
            _jobs[job_id]["audio_duration"] = round(audio_sec, 1)
        _set_stage_estimate(job_id, "transcribing", audio_sec * _TRANSCRIBE_RATE)

        _set_stage(job_id, "transcribing")
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_t = ex.submit(
                transcribe,
                audio_path,
                opts.get("language", "auto"),
                job_dir,
                True,
                lambda d, t: _set_transcribe_progress(job_id, d, t),
            )
            f_s = ex.submit(detect_scenes, video_path, job_dir / "screenshots")
            transcript = f_t.result()
            scenes = f_s.result()

        _set_stage(job_id, "analyzing")
        outline = analyze(transcript, scenes, opts.get("video_type") or None)
        outline = _append_source_slide(outline, url, info.get("title", ""), video_id)
        (job_dir / "outline.json").write_text(
            json.dumps(outline, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

        export_knowledge(outline, transcript, info, job_dir)

        _set_stage(job_id, "generating_slides")
        slides_url = generate_slides(
            outline,
            scenes if not opts.get("no_screenshots") else [],
        )
        presentation_id = slides_url.split("/d/")[1].split("/")[0]

        _set_stage(job_id, "exporting")
        DOWNLOADS_DIR.mkdir(parents=True, exist_ok=True)
        title = outline.get("presentation_title") or info.get("title") or video_id
        safe_title = _safe_filename(title, video_id)
        creds = _get_credentials()
        drive = build("drive", "v3", credentials=creds)
        files: dict[str, str] = {}
        for fmt, mime in _EXPORT_MIME.items():
            data = drive.files().export(fileId=presentation_id, mimeType=mime).execute()
            dest = DOWNLOADS_DIR / f"{safe_title}.{fmt}"
            dest.write_bytes(data)
            files[fmt] = str(dest)

        _set_stage(job_id, "completed")
        with _jobs_lock:
            _jobs[job_id].update({
                "status": "done",
                "message": _STAGE_LABEL["completed"],
                "slides_url": slides_url,
                "presentation_id": presentation_id,
                "title": title,
                "files": files,
                "ended_at": time.time(),
            })
        _persist_job(job_id)
    except Exception as e:
        now = time.time()
        with _jobs_lock:
            if job_id in _jobs:
                job = _jobs[job_id]
                cur_stage = job.get("stage")
                cur_start = job.get("_stage_start")
                if cur_stage in _TIMED_STAGES and cur_start:
                    job.setdefault("stages_elapsed", {})[cur_stage] = now - cur_start
                job.update({
                    "status": "failed",
                    "stage": "failed",
                    "message": f"失敗：{e}",
                    "error": str(e),
                    "ended_at": now,
                })
        _persist_job(job_id)


@app.get("/health")
def health():
    return {"ok": True}


@app.get("/", response_class=HTMLResponse)
@app.get("/ui", response_class=HTMLResponse)
def ui():
    return (Path(__file__).parent / "ui.html").read_text(encoding="utf-8")


@app.post("/jobs")
def create_job(req: JobRequest):
    job_id = uuid.uuid4().hex[:12]
    with _jobs_lock:
        _jobs[job_id] = {
            "job_id": job_id,
            "status": "running",
            "stage": "queued",
            "message": _STAGE_LABEL["queued"],
            "url": req.url,
        }
    _persist_job(job_id)
    threading.Thread(
        target=_run_job,
        args=(job_id, req.url, {
            "no_screenshots": req.no_screenshots,
            "language": req.language,
            "video_type": req.video_type,
        }),
        daemon=True,
    ).start()
    return {"job_id": job_id}


@app.get("/jobs")
def list_jobs():
    with _jobs_lock:
        raw = list(_jobs.values())
        items = sorted(
            ({k: v for k, v in j.items() if not k.startswith("_")} for j in raw),
            key=lambda x: x.get("started_at", 0),
            reverse=True,
        )
        dirs = {j.get("job_id"): _resolve_job_dir(j) for j in raw}
    for it in items:
        d = dirs.get(it.get("job_id"))
        it["source_exists"] = bool(d and d.exists())
    return {"jobs": items}


@app.get("/jobs/{job_id}")
def get_job(job_id: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "job not found")
        out = {k: v for k, v in job.items() if not k.startswith("_")}
        now = time.time()
        cur_stage = job.get("stage")
        cur_start = job.get("_stage_start")
        if job.get("status") == "running" and cur_stage in _TIMED_STAGES and cur_start:
            out["current_stage_elapsed"] = now - cur_start
        started_at = job.get("started_at")
        if started_at:
            ended_at = job.get("ended_at") or now
            out["total_elapsed"] = ended_at - started_at

        est = dict(job.get("_stage_estimate") or _STAGE_ESTIMATE)
        prog = job.get("progress")
        if prog:
            out["progress"] = dict(prog, age=now - prog["updated_at"])
            # 有實測進度就用實測速度外推，取代事前估算
            if cur_stage == "transcribing" and cur_start and prog["ratio"] >= 0.05:
                est["transcribing"] = round((now - cur_start) / prog["ratio"])
        out["stages_estimate"] = est
        out["estimated_total"] = sum(est.values())
        return out


@app.post("/jobs/{job_id}/archive")
def archive_job(job_id: str, req: ArchiveRequest):
    with _jobs_lock:
        job = _jobs.get(job_id)
        if not job:
            raise HTTPException(404, "job not found")
        if job.get("status") == "running":
            raise HTTPException(409, "此任務還在執行中，不能搬移")
        archived = job.get("archived")
        src = _resolve_job_dir(job)

    if archived:
        return {"ok": True, "archived": archived, "message": "先前已搬移"}
    if src is None:
        raise HTTPException(409, "此任務沒有素材目錄")
    if not src.exists():
        raise HTTPException(409, f"原始素材已不存在：{src}")

    info = _move_to_warehouse(src, req.dest)
    with _jobs_lock:
        if job_id in _jobs:
            _jobs[job_id]["archived"] = info
    _persist_job(job_id)
    return {"ok": True, "archived": info}


@app.get("/orphans")
def list_orphans():
    items = [
        {"name": d.name, "path": str(d), "bytes": _dir_size(d)}
        for d in _orphan_dirs()
    ]
    return {"orphans": items, "total_bytes": sum(i["bytes"] for i in items)}


@app.post("/orphans/archive")
def archive_orphan(req: OrphanArchiveRequest):
    src = next((d for d in _orphan_dirs() if d.name == req.name), None)
    if src is None:
        raise HTTPException(404, f"找不到未列管素材：{req.name}")
    return {"ok": True, "archived": _move_to_warehouse(src, req.dest)}


@app.get("/download/{job_id}/{fmt}")
def download_file(job_id: str, fmt: str):
    with _jobs_lock:
        job = _jobs.get(job_id)
    if not job:
        raise HTTPException(404, "job not found")
    if job.get("status") != "done":
        raise HTTPException(409, "job not finished")

    if fmt == "slides":
        return RedirectResponse(url=job["slides_url"])

    if fmt not in _EXPORT_MIME:
        raise HTTPException(400, "unsupported format")

    files = job.get("files", {})
    path_str = files.get(fmt)
    if not path_str or not Path(path_str).exists():
        raise HTTPException(404, "file not found")

    path = Path(path_str)
    return FileResponse(
        str(path),
        media_type=_EXPORT_MIME[fmt],
        filename=path.name,
    )


_load_persisted_jobs()


if __name__ == "__main__":
    import uvicorn
    uvicorn.run("server:app", host="0.0.0.0", port=8001, reload=False)

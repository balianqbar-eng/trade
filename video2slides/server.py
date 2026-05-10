import json
import shutil
import sys
import threading
import time
import uuid
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

# 各階段預估秒數（依據 30 分鐘影片的經驗值，僅作為 ETA 參考）
_STAGE_ESTIMATE = {
    "downloading": 45,
    "extracting_audio": 8,
    "transcribing": 180,
    "analyzing": 25,
    "generating_slides": 20,
    "exporting": 12,
}

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
        job["_stage_start"] = now
        if "started_at" not in job:
            job["started_at"] = now
    _persist_job(job_id)


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

        _set_stage(job_id, "transcribing")
        with ThreadPoolExecutor(max_workers=2) as ex:
            f_t = ex.submit(transcribe, audio_path, opts.get("language", "auto"), job_dir)
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
        items = sorted(
            ({k: v for k, v in j.items() if not k.startswith("_")} for j in _jobs.values()),
            key=lambda x: x.get("started_at", 0),
            reverse=True,
        )
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
        out["stages_estimate"] = _STAGE_ESTIMATE
        out["estimated_total"] = sum(_STAGE_ESTIMATE.values())
        return out


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

import json
import subprocess
from collections.abc import Callable
from pathlib import Path

import mlx_whisper
import numpy as np
import torch
from silero_vad import get_speech_timestamps, load_silero_vad
from rich.progress import BarColumn, Progress, TextColumn

from .config import settings

SAMPLE_RATE = 16000


def transcribe(
    audio_path: Path,
    language: str | None = None,
    output_dir: Path | None = None,
    use_cache: bool = True,
    progress_cb: Callable[[float, float], None] | None = None,
) -> dict:
    out = output_dir or (settings.output_dir / "transcripts")
    out.mkdir(parents=True, exist_ok=True)

    cached = out / f"{audio_path.stem}.json"
    if use_cache and cached.exists():
        return json.loads(cached.read_text(encoding="utf-8"))

    lang = None if language == "auto" else language

    audio = _load_audio(audio_path)
    total_sec = len(audio) / SAMPLE_RATE
    speech = _speech_segments(audio)
    if progress_cb:
        progress_cb(0.0, total_sec)

    segments = []
    detected_lang = lang
    with Progress(
        TextColumn("[progress.description]{task.description}"),
        BarColumn(),
        TextColumn("{task.completed}/{task.total}"),
        transient=True,
    ) as progress:
        task = progress.add_task("語音轉文字中...", total=len(speech))
        for sp in speech:
            offset = sp["start"] / SAMPLE_RATE
            chunk = audio[sp["start"]:sp["end"]]
            result = mlx_whisper.transcribe(
                chunk,
                path_or_hf_repo=settings.whisper_model,
                language=lang,
                condition_on_previous_text=False,
                word_timestamps=False,
                verbose=None,
            )
            detected_lang = detected_lang or result.get("language")
            for s in result.get("segments", []):
                text = s["text"].strip()
                if not text:
                    continue
                segments.append({
                    "start": round(offset + s["start"], 3),
                    "end": round(offset + s["end"], 3),
                    "text": text,
                    "words": [],
                })
            progress.advance(task)
            if progress_cb:
                progress_cb(sp["end"] / SAMPLE_RATE, total_sec)

    full_text = " ".join(s["text"] for s in segments)
    result = {
        "language": detected_lang or "unknown",
        "segments": segments,
        "full_text": full_text,
    }

    stem = audio_path.stem
    _save_json(result, out / f"{stem}.json")
    _save_srt(segments, out / f"{stem}.srt")

    return result


def _load_audio(path: Path) -> np.ndarray:
    cmd = [
        "ffmpeg", "-nostdin", "-threads", "0",
        "-i", str(path),
        "-f", "f32le", "-ac", "1", "-ar", str(SAMPLE_RATE), "-",
    ]
    pcm = subprocess.run(cmd, capture_output=True, check=True).stdout
    return np.frombuffer(pcm, np.float32).copy()


def _speech_segments(audio: np.ndarray) -> list[dict]:
    model = load_silero_vad()
    return get_speech_timestamps(
        torch.from_numpy(audio),
        model,
        sampling_rate=SAMPLE_RATE,
        min_silence_duration_ms=500,
        max_speech_duration_s=30,
        speech_pad_ms=200,
        return_seconds=False,
    )


def _save_json(data: dict, path: Path) -> None:
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")


def _save_srt(segments: list[dict], path: Path) -> None:
    lines = []
    for i, seg in enumerate(segments, 1):
        lines.append(str(i))
        lines.append(f"{_fmt_time(seg['start'])} --> {_fmt_time(seg['end'])}")
        lines.append(seg["text"])
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def _fmt_time(seconds: float) -> str:
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = int(seconds % 60)
    ms = int((seconds % 1) * 1000)
    return f"{h:02d}:{m:02d}:{s:02d},{ms:03d}"

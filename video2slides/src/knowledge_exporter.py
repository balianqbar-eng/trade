import json
import re
import threading
from datetime import datetime
from pathlib import Path

from google import genai

from .config import settings

GEMINI_MODEL = "gemini-2.5-flash-lite"

CATEGORIES = ["財經", "心理學", "生活", "AI運用", "其他"]

KNOWLEDGE_DIR = settings.output_dir / "knowledge"
INDEX_PATH = KNOWLEDGE_DIR / "index.json"
_index_lock = threading.Lock()


def export_knowledge(outline: dict, transcript: dict, video_info: dict, job_dir: Path) -> Path:
    client = genai.Client(api_key=settings.gemini_api_key)
    category = _classify_category(client, outline)

    md = _build_markdown(outline, transcript, video_info, category)

    title = outline.get("presentation_title") or video_info.get("title") or job_dir.name
    safe_title = _safe_filename(title)

    category_dir = KNOWLEDGE_DIR / category
    category_dir.mkdir(parents=True, exist_ok=True)

    dest = category_dir / f"{safe_title}_knowledge.md"
    dest.write_text(md, encoding="utf-8")

    _update_index(title, category, dest, video_info)

    return dest


def _classify_category(client, outline: dict) -> str:
    title = outline.get("presentation_title", "")
    bullets = []
    for slide in outline.get("slides", []):
        if slide.get("type") in ("content", "key_takeaways", "summary"):
            bullets.extend(slide.get("bullets", []))
            if len(bullets) > 20:
                break

    content = f"標題：{title}\n重點：\n" + "\n".join(f"- {b}" for b in bullets[:20])

    prompt = f"""根據以下學習內容，從固定類別中選出最符合的一個。

類別選項：{', '.join(CATEGORIES)}

內容：
{content}

只回覆一個 JSON，格式為：{{"category": "財經"}}"""

    try:
        response = client.models.generate_content(model=GEMINI_MODEL, contents=prompt)
        match = re.search(r'\{"category":\s*"([^"]+)"\}', response.text)
        if match and match.group(1) in CATEGORIES:
            return match.group(1)
    except Exception:
        pass
    return "其他"


def _build_markdown(outline: dict, transcript: dict, video_info: dict, category: str) -> str:
    title = outline.get("presentation_title", "")
    source_url = video_info.get("url") or video_info.get("webpage_url", "")
    processed_at = datetime.now().strftime("%Y-%m-%d %H:%M")

    lines = [
        f"---",
        f"title: {title}",
        f"category: {category}",
        f"source: {source_url}",
        f"processed_at: {processed_at}",
        f"---",
        f"",
        f"# {title}",
        f"",
    ]

    type_handlers = {
        "learning_objectives": ("## 學習目標", True),
        "prerequisites": ("## 前置知識", True),
        "key_takeaways": ("## 重點提醒", True),
        "practice_questions": ("## 練習題", True),
        "summary": ("## 總結", True),
    }

    content_slides = []
    section_blocks: dict[str, list[str]] = {}

    for slide in outline.get("slides", []):
        slide_type = slide.get("type", "")

        if slide_type in type_handlers:
            header, _ = type_handlers[slide_type]
            block = [header]
            for b in slide.get("bullets", []):
                block.append(f"- {b}")
            section_blocks[slide_type] = block

        elif slide_type == "content":
            content_slides.append(slide)

    for section_type in ["learning_objectives", "prerequisites"]:
        if section_type in section_blocks:
            lines.extend(section_blocks[section_type])
            lines.append("")

    if content_slides:
        lines.append("## 核心內容")
        lines.append("")
        for slide in content_slides:
            lines.append(f"### {slide.get('title', '')}")
            for b in slide.get("bullets", []):
                lines.append(f"- {b}")
            notes = slide.get("speaker_notes", "").strip()
            if notes:
                lines.append(f"> {notes}")
            lines.append("")

    for section_type in ["key_takeaways", "practice_questions", "summary"]:
        if section_type in section_blocks:
            lines.extend(section_blocks[section_type])
            lines.append("")

    lines.append("---")
    lines.append("## 完整逐字稿")
    lines.append("")

    full_text = " ".join(
        seg["text"].strip()
        for seg in transcript.get("segments", [])
        if seg.get("text", "").strip()
    )
    lines.append(full_text)

    return "\n".join(lines)


def _update_index(title: str, category: str, dest: Path, video_info: dict):
    with _index_lock:
        if INDEX_PATH.exists():
            index = json.loads(INDEX_PATH.read_text(encoding="utf-8"))
        else:
            index = {"entries": []}

        index["entries"] = [
            e for e in index.get("entries", [])
            if e.get("file") != str(dest)
        ]
        index["entries"].append({
            "title": title,
            "category": category,
            "file": str(dest),
            "source": video_info.get("url") or video_info.get("webpage_url", ""),
            "processed_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        })
        index["updated_at"] = datetime.now().strftime("%Y-%m-%d %H:%M")

        KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)
        INDEX_PATH.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")


def _safe_filename(title: str) -> str:
    keep = " -_()[]"
    cleaned = "".join(c for c in title if c.isalnum() or c in keep or "一" <= c <= "鿿").strip()
    return cleaned[:60] or "knowledge"

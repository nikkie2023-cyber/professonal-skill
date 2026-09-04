import json
import re
import uuid
from pathlib import Path
from typing import Any


DATA_DIR = Path(__file__).resolve().parents[1] / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
FRAME_DIR = DATA_DIR / "frames"
REPORT_DIR = DATA_DIR / "reports"
REFERENCE_DIR = DATA_DIR / "references"


def ensure_data_dirs() -> None:
    for folder in (UPLOAD_DIR, FRAME_DIR, REPORT_DIR, REFERENCE_DIR):
        folder.mkdir(parents=True, exist_ok=True)


def new_id() -> str:
    return uuid.uuid4().hex


def safe_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]+", "_", name or "video.mp4")
    return cleaned[:120] or "video.mp4"


def save_upload(filename: str, content: bytes) -> tuple[str, Path]:
    ensure_data_dirs()
    asset_id = new_id()
    path = UPLOAD_DIR / f"{asset_id}_{safe_filename(filename)}"
    path.write_bytes(content)
    return asset_id, path


def save_report(report_id: str, report: dict[str, Any]) -> Path:
    ensure_data_dirs()
    path = REPORT_DIR / f"{report_id}.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def load_report(report_id: str) -> dict[str, Any] | None:
    path = REPORT_DIR / f"{report_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def save_reference(reference: dict[str, Any]) -> dict[str, Any]:
    ensure_data_dirs()
    record = dict(reference)
    record["reference_id"] = new_id()
    record["created_at"] = __import__("datetime").datetime.now().isoformat(timespec="seconds")
    path = REFERENCE_DIR / f"{record['reference_id']}.json"
    path.write_text(json.dumps(record, ensure_ascii=False, indent=2), encoding="utf-8")
    return record


def load_reference(reference_id: str) -> dict[str, Any] | None:
    path = REFERENCE_DIR / f"{reference_id}.json"
    if not path.exists():
        return None
    return json.loads(path.read_text(encoding="utf-8"))

"""Background analysis jobs used by the web UI.

The original endpoint intentionally remains synchronous for compatibility with
existing clients and tests.  The browser uses the job API so long-running
video/model work does not hold a request open until the browser times out.
"""

from __future__ import annotations

import shutil
import subprocess
import threading
import time
from pathlib import Path
from typing import Any

from .analyzer import analyze_video
from .storage import save_report


_JOBS: dict[str, dict[str, Any]] = {}
_JOBS_LOCK = threading.Lock()
_JOB_TTL_SECONDS = 60 * 60


def _estimate_seconds(video_path: Path) -> int:
    """Return a deliberately broad estimate, never a fake countdown."""
    duration = 0.0
    ffprobe = shutil.which("ffprobe")
    if ffprobe:
        try:
            result = subprocess.run(
                [ffprobe, "-v", "error", "-show_entries", "format=duration",
                 "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)],
                capture_output=True, text=True, check=False, timeout=15,
            )
            duration = max(0.0, float(result.stdout.strip() or 0))
        except (OSError, ValueError, subprocess.TimeoutExpired):
            duration = 0.0
    size_mb = video_path.stat().st_size / (1024 * 1024) if video_path.exists() else 0.0
    return max(60, min(600, int(45 + duration * 0.8 + size_mb * 2)))


def _cleanup_old_jobs() -> None:
    cutoff = time.time() - _JOB_TTL_SECONDS
    with _JOBS_LOCK:
        for job_id, value in list(_JOBS.items()):
            if value.get("updated_at", 0) < cutoff and value.get("status") in {"completed", "failed"}:
                _JOBS.pop(job_id, None)


def _update(job_id: str, **changes: Any) -> None:
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        if job:
            job.update(changes)
            job["updated_at"] = time.time()


def get_job(job_id: str) -> dict[str, Any] | None:
    _cleanup_old_jobs()
    with _JOBS_LOCK:
        job = _JOBS.get(job_id)
        return dict(job) if job else None


def start_analysis_job(
    job_id: str,
    asset_id: str,
    video_path: Path,
    filename: str,
    goal: str,
    profile: dict[str, Any],
    public_url: str | None = None,
    input_source: str | None = None,
) -> dict[str, Any]:
    _cleanup_old_jobs()
    estimate = _estimate_seconds(video_path)
    now = time.time()
    job = {
        "job_id": job_id,
        "status": "queued",
        "stage": "queued",
        "progress": 0,
        "estimated_seconds": estimate,
        "asset_id": asset_id,
        "filename": filename,
        "created_at": now,
        "updated_at": now,
    }
    with _JOBS_LOCK:
        _JOBS[job_id] = job

    def worker() -> None:
        _update(job_id, status="processing", stage="metadata", progress=5)

        def progress(stage: str, value: float) -> None:
            _update(job_id, status="processing", stage=stage, progress=max(5, min(95, int(value))))

        try:
            report = analyze_video(
                asset_id, video_path, filename, goal, profile,
                public_url=public_url, progress_callback=progress,
            )
            if input_source:
                report["input_source"] = input_source
            save_report(report["report_id"], report)
            _update(job_id, status="completed", stage="completed", progress=100,
                    report_id=report["report_id"], analysis_status=report.get("analysis_status"))
        except Exception as error:  # keep details local, return a safe message to browser
            print(f"analysis_job_error: {type(error).__name__}: {error}", flush=True)
            _update(job_id, status="failed", stage="failed", progress=100,
                    error="视频分析失败，请查看服务端日志或改用较短视频重试。")

    thread = threading.Thread(target=worker, name=f"analysis-{job_id[:8]}", daemon=True)
    thread.start()
    return {key: value for key, value in job.items() if key not in {"created_at", "updated_at"}}

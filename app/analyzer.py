import os
import shutil
import subprocess
from pathlib import Path
from typing import Any, Callable

from .config import settings
from .providers import call_deepseek
from .qwen_provider import call_qwen_video
from .storage import FRAME_DIR, new_id

ALLOWED_GOALS = {"commerce", "growth"}
COMMERCE_STAGES = ["流量钩子", "目标人群", "用户痛点", "场景放大", "商品引入", "卖点展示", "效果证明", "信任建立", "异议处理", "价格利益", "行动理由", "CTA"]
LEVELS = ["可直接复刻", "改造后复刻", "不建议复刻"]


def _duration_seconds(video_path: Path) -> float | None:
    ffprobe = settings.ffprobe_path or shutil.which("ffprobe")
    if not ffprobe:
        return None
    try:
        result = subprocess.run([ffprobe, "-v", "error", "-show_entries", "format=duration", "-of", "default=noprint_wrappers=1:nokey=1", str(video_path)], capture_output=True, text=True, check=False, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    try:
        return round(float(result.stdout.strip()), 2)
    except (TypeError, ValueError):
        return None


def _format_time(value: Any) -> str:
    try:
        seconds = max(0.0, float(value))
        minutes = int(seconds // 60)
        remaining = seconds - minutes * 60
        return f"{minutes:02d}:{remaining:05.2f}"
    except (TypeError, ValueError):
        text = str(value or "未识别")
        return text


def _time_range(start: Any, end: Any) -> str:
    return f"{_format_time(start)}–{_format_time(end)}"


def _seconds(value: Any) -> float:
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "0").replace("–", "-")
    try:
        parts = [float(x) for x in text.split(":")]
        if len(parts) == 2:
            return parts[0] * 60 + parts[1]
        return parts[0]
    except (TypeError, ValueError):
        return 0.0


def extract_frames(video_path: Path, asset_id: str, timestamps: list[float]) -> list[dict[str, Any]]:
    ffmpeg = settings.ffmpeg_path or shutil.which("ffmpeg")
    folder = FRAME_DIR / asset_id
    folder.mkdir(parents=True, exist_ok=True)
    frames: list[dict[str, Any]] = []
    for index, timestamp in enumerate(timestamps):
        filename = f"frame_{index:02d}_{timestamp:.2f}.jpg"
        output = folder / filename
        status = "unavailable"
        if ffmpeg:
            try:
                result = subprocess.run([ffmpeg, "-y", "-ss", str(timestamp), "-i", str(video_path), "-frames:v", "1", "-q:v", "3", str(output)], capture_output=True, check=False, timeout=30)
                if result.returncode == 0 and output.exists():
                    status = "ready"
            except (OSError, subprocess.TimeoutExpired):
                status = "unavailable"
        frames.append({"timestamp": timestamp, "filename": filename, "status": status, "url": f"/frames/{asset_id}/{filename}" if status == "ready" else ""})
    return frames


def _mock_timeline(goal: str, duration: float | None) -> list[dict[str, Any]]:
    total = duration or 30.0
    points = sorted(set([0.0, min(3.0, total), min(8.0, total), min(total * 0.55, total), min(total * 0.8, total)]))
    if goal == "commerce":
        labels = ["流量钩子", "商品引入", "卖点展示", "异议处理", "价格利益"]
        actions = ["锁定目标人群并提出痛点", "展示商品外观或核心卖点", "通过画面提供卖点证据", "处理购买顾虑", "展示价格并引导下一步"]
    else:
        labels = ["Hook", "身份与问题", "过程推进", "结果兑现", "关注理由"]
        actions = ["阻止划走", "建立共鸣", "维持观看", "兑现承诺", "形成关注期待"]
    return [{"timestamp": t, "label": labels[i], "action": actions[i], "evidence": "待视频模型确认", "confidence": "mock", "replication_level": ("可直接复刻" if i in (0, 2) else "改造后复刻" if i == 1 else "不建议复刻" if goal == "commerce" and i == 3 else "可直接复刻")} for i, t in enumerate(points)]


def _level(value: Any) -> str:
    text = str(value or "")
    if "不建议" in text or "不可" in text:
        return "不建议复刻"
    if "改造" in text or "条件" in text:
        return "改造后复刻"
    return "可直接复刻"


def _stage(value: Any, index: int) -> str:
    text = str(value or "")
    for stage in COMMERCE_STAGES:
        if stage in text:
            return stage
    return COMMERCE_STAGES[min(index, len(COMMERCE_STAGES) - 1)]


def _frame_for(index: int, frames: list[dict[str, Any]]) -> dict[str, Any]:
    return frames[index] if index < len(frames) else {"status": "unavailable", "url": "", "filename": ""}


def _as_list(value: Any, fallback: list[Any] | None = None) -> list[Any]:
    if isinstance(value, list):
        return value
    if isinstance(value, str) and value.strip():
        return [part.strip() for part in value.replace("→", "➜").replace("➡", "➜").split("➜") if part.strip()]
    return fallback or []


def _shot_from_item(item: dict[str, Any], index: int, frames: list[dict[str, Any]], duration: float | None) -> dict[str, Any]:
    start = item.get("start_time", item.get("timestamp", 0))
    end = item.get("end_time")
    if end is None:
        end = min(float(start or 0) + 2.0, duration or float(start or 0) + 2.0)
    frame = _frame_for(index, frames)
    visual = item.get("visual_description", item.get("visual", item.get("evidence", "未识别")))
    spoken = item.get("spoken_text", item.get("spoken_or_text", "未识别"))
    subtitle = item.get("subtitle_text", item.get("subtitle", "未识别"))
    level = _level(item.get("replication_level", item.get("replicable", "")))
    reason = item.get("replication_reason", item.get("reason", "根据镜头结构、证据和用户拍摄条件判断"))
    advice = item.get("replication_advice", item.get("adaptation", "保留销售结构，换成用户真实商品和可拍摄场景"))
    alternative = item.get("alternative_plan", "将原视频依赖的个人条件替换为用户真实可验证的画面证据")
    if level == "可直接复刻":
        alternative = item.get("alternative_plan", "无需额外替换；使用用户自己的商品和真实素材")
    return {
        "shot_id": index + 1, "start_time": _format_time(start), "end_time": _format_time(end),
        "time_range": _time_range(start, end), "screenshot_url": frame.get("url", "") or (item.get("screenshot_url", "") if str(item.get("screenshot_url", "")).startswith("/frames/") else ""),
        "screenshot_status": frame.get("status", "unavailable"), "visual_description": visual or "未识别",
        "shot_size": item.get("shot_size", "未识别"), "spoken_text": spoken or "未识别", "subtitle_text": subtitle or "未识别",
        "product_action": item.get("product_action", "未识别"), "sales_function": item.get("sales_function", item.get("action", "未识别")),
        "effective_reason": item.get("effective_reason", item.get("why_effective", item.get("sales_function", "未识别"))),
        "sales_stage": _stage(item.get("sales_stage", item.get("label")), index), "replication_level": level,
        "replication_reason": reason or "未识别", "replication_advice": advice or "未识别",
        "non_replicable_reason": item.get("non_replicable_reason", "未识别"), "alternative_plan": alternative,
        "evidence_status": item.get("evidence_status", "已从视频观察"), "improvement_note": item.get("improvement_note", ""),
    }


def _script_from_shots(shots: list[dict[str, Any]]) -> dict[str, Any]:
    checklist = []
    for shot in shots:
        advice = shot.get("replication_advice") or shot.get("alternative_plan") or shot.get("visual_description")
        checklist.append(f"镜头{shot['shot_id']:02d}｜{advice}")
    return {"shooting_checklist": checklist, "shots": [{
        "shot_id": shot["shot_id"], "time_range": shot["time_range"], "shot_type": shot.get("shot_size", "未识别"),
        "visual": shot.get("replication_advice", shot.get("visual_description", "未识别")), "voiceover": "请根据真实商品和体验填写，不要虚构", "subtitle": shot.get("subtitle_text", "未识别"),
        "sound_effect": "轻微转场或环境音，按原视频作用调整", "music": "低音量背景音乐", "editing": "按该镜头时间范围剪辑，保留商品证据", "materials": [shot.get("visual_description", "未识别")],
    } for shot in shots]}


def normalize_commerce_result(result: dict[str, Any] | None, asset_id: str, profile: dict[str, Any], filename: str, frames: list[dict[str, Any]], duration: float | None, observations: dict[str, Any] | None = None) -> dict[str, Any]:
    raw = result if isinstance(result, dict) else {}
    raw_shots = raw.get("shots") if isinstance(raw.get("shots"), list) else raw.get("timeline", [])
    if not raw_shots:
        raw_shots = _mock_timeline("commerce", duration)
    shots = [_shot_from_item(item if isinstance(item, dict) else {}, i, frames, duration) for i, item in enumerate(raw_shots)]
    summary = raw.get("video_summary", {}) if isinstance(raw.get("video_summary"), dict) else {}
    nodes = raw.get("key_nodes", {}) if isinstance(raw.get("key_nodes"), dict) else {}
    findings = raw.get("overall_findings", {}) if isinstance(raw.get("overall_findings"), dict) else {}
    script = raw.get("user_script") if isinstance(raw.get("user_script"), dict) else _script_from_shots(shots)
    cover_raw = raw.get("cover_analysis") if isinstance(raw.get("cover_analysis"), dict) else {}
    cover_analysis = {
        "cover_available": cover_raw.get("cover_available", "未识别"),
        "cover_source": cover_raw.get("cover_source", "视频首帧/模型可见封面"),
        "main_subject": cover_raw.get("main_subject", "未识别"),
        "cover_text": cover_raw.get("cover_text", "未识别"),
        "product_or_pain_point": cover_raw.get("product_or_pain_point", "未识别"),
        "target_audience": cover_raw.get("target_audience", "未识别"),
        "click_reason": cover_raw.get("click_reason", "未识别"),
        "visual_hierarchy": cover_raw.get("visual_hierarchy", "未识别"),
        "text_readability": cover_raw.get("text_readability", "未识别"),
        "promise_match": cover_raw.get("promise_match", "未识别"),
        "replication_level": _level(cover_raw.get("replication_level", "")),
        "replication_reason": cover_raw.get("replication_reason", "未识别"),
        "adaptation_advice": cover_raw.get("adaptation_advice", "未识别"),
        "risks": cover_raw.get("risks", "未识别"),
    }
    report = {
        "report_id": new_id(), "asset_id": asset_id, "mode": "commerce", "filename": filename,
        "analysis_status": "mock", "duration_seconds": duration, "media_url": f"/uploads/{asset_id}/{filename}",
        "user_adaptation": {"profile": profile}, "video_observations": observations or {}, "cover_analysis": cover_analysis,
        "video_summary": {"duration": summary.get("duration", _format_time(duration or 0)), "product_category": summary.get("product_category", "未识别"), "video_type": summary.get("video_type", "未识别"), "target_audience": summary.get("target_audience", "未识别"), "core_pain_point": summary.get("core_pain_point", "未识别"), "core_selling_point": summary.get("core_selling_point", "未识别"), "sales_path": _as_list(summary.get("sales_path"), [s["sales_stage"] for s in shots])},
        "key_nodes": {"product_first_appearance": nodes.get("product_first_appearance", "未识别"), "core_selling_point_appearance": nodes.get("core_selling_point_appearance", "未识别"), "price_appearance": nodes.get("price_appearance", "未识别"), "cta_appearance": nodes.get("cta_appearance", "未识别")},
        "shots": shots, "overall_findings": {"strongest_conversion_design": findings.get("strongest_conversion_design", [s["sales_function"] for s in shots[:3]]), "missing_evidence": findings.get("missing_evidence", []), "non_replicable_elements": findings.get("non_replicable_elements", []), "recommended_adjustments": findings.get("recommended_adjustments", [])},
        "user_script": script,
        "timeline": [{"timestamp": s["start_time"], "label": s["sales_stage"], "action": s["sales_function"], "frame": _frame_for(i, frames)} for i, s in enumerate(shots)],
        "script": script.get("shots", []), "replicable": [s for s in shots if s["replication_level"] == "可直接复刻"], "non_replicable": [s for s in shots if s["replication_level"] == "不建议复刻"],
        "summary": "已完成结构化带货拆解；模型未确认的内容均标记为未识别。", "next_action": "从逐镜头表格选择可复刻元素，生成用户版本拍摄清单。",
    }
    return report


def build_mock_report(asset_id: str, goal: str, profile: dict[str, Any], filename: str, frames: list[dict[str, Any]], duration: float | None) -> dict[str, Any]:
    if goal == "commerce":
        return normalize_commerce_result(None, asset_id, profile, filename, frames, duration)
    timeline = _mock_timeline(goal, duration)
    return {"report_id": new_id(), "asset_id": asset_id, "mode": goal, "filename": filename, "analysis_status": "mock", "duration_seconds": duration, "timeline": timeline, "script": [], "replicable": [], "non_replicable": [], "user_adaptation": {"profile": profile}, "summary": "当前为演示分析。"}


def analyze_video(
    asset_id: str,
    video_path: Path,
    filename: str,
    goal: str,
    profile: dict[str, Any],
    public_url: str | None = None,
    progress_callback: Callable[[str, float], None] | None = None,
) -> dict[str, Any]:
    if goal not in ALLOWED_GOALS:
        raise ValueError("goal must be commerce or growth")
    notify = progress_callback or (lambda _stage, _progress: None)
    notify("metadata", 8)
    duration = _duration_seconds(video_path)
    base_timeline = _mock_timeline(goal, duration)
    notify("extracting_frames", 12)
    if duration is None:
        frames = [{"timestamp": float(x["timestamp"]), "filename": "", "status": "unavailable", "url": ""} for x in base_timeline]
    else:
        frames = extract_frames(video_path, asset_id, [float(x["timestamp"]) for x in base_timeline])
    notify("vision_analysis", 25)
    qwen = call_qwen_video(video_path, public_url, goal, profile)
    notify("vision_analysis", 62)
    if goal != "commerce":
        report = build_mock_report(asset_id, goal, profile, filename, frames, duration)
        if qwen:
            report["analysis_status"] = "qwen_video"
            report["timeline"] = qwen.get("timeline", report["timeline"])
        notify("finalizing", 90)
        return report
    if qwen:
        observed = qwen.get("shots") if isinstance(qwen.get("shots"), list) else qwen.get("timeline")
        if isinstance(observed, list) and observed:
            # Avoid an accidental model response with hundreds of nodes turning
            # into hundreds of separate ffmpeg processes.
            observed = observed[:32]
            observed_starts = [_seconds(item.get("start_time", item.get("timestamp", 0))) for item in observed if isinstance(item, dict)]
            if observed_starts:
                notify("extracting_frames", 70)
                frames = extract_frames(video_path, asset_id, observed_starts) if duration is not None else frames
    notify("structuring_report", 78)
    report = normalize_commerce_result(qwen, asset_id, profile, filename, frames, duration, qwen)
    report["analysis_status"] = "qwen_video" if qwen else "mock"
    # DeepSeek is a second network round-trip.  For long videos Qwen's
    # structured result is already usable; skipping this optional polish keeps
    # a four-minute test from waiting for two model timeouts in sequence.
    max_enhance_seconds = float(os.getenv("DEEPSEEK_ENHANCE_MAX_SECONDS", "90"))
    enhanced = call_deepseek(report) if (duration is None or duration <= max_enhance_seconds) else None
    notify("text_analysis", 88)
    if enhanced:
        report = normalize_commerce_result(enhanced, asset_id, profile, filename, frames, duration, qwen or {})
        report["analysis_status"] = "qwen_video+deepseek" if qwen else "deepseek_text"
    notify("finalizing", 96)
    return report

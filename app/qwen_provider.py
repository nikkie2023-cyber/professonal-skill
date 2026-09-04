import base64
import json
import os
import shutil
import subprocess
import tempfile
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any

from .prompts import COMMERCE_SYSTEM_PROMPT, COMMERCE_USER_INSTRUCTION, GROWTH_SYSTEM_PROMPT


def _json_from_content(content: str) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "").strip()
    try:
        value = json.loads(text)
        return value if isinstance(value, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                value = json.loads(text[start:end + 1])
                return value if isinstance(value, dict) else None
            except json.JSONDecodeError:
                return None
        return None


MAX_INLINE_VIDEO_BYTES = 8 * 1024 * 1024


def _make_model_preview(path: Path) -> Path | None:
    """Create a small, still-audible preview for local videos over 8MB."""
    ffmpeg = os.getenv("FFMPEG_PATH") or shutil.which("ffmpeg")
    if not ffmpeg:
        return None
    fd, name = tempfile.mkstemp(prefix="content_workbench_qwen_", suffix=".mp4")
    os.close(fd)
    output = Path(name)
    profiles = [("360", "180k", "32k", "8"), ("240", "100k", "24k", "6")]
    try:
        for height, video_bitrate, audio_bitrate, fps in profiles:
            command = [
                ffmpeg, "-y", "-i", str(path),
                "-vf", f"scale=-2:{height},fps={fps}",
                "-c:v", "libx264", "-preset", "veryfast", "-b:v", video_bitrate,
                "-maxrate", video_bitrate, "-bufsize", video_bitrate,
                "-c:a", "aac", "-b:a", audio_bitrate, "-movflags", "+faststart",
                str(output),
            ]
            try:
                result = subprocess.run(command, capture_output=True, check=False, timeout=180)
            except (OSError, subprocess.TimeoutExpired):
                result = None
            if result is not None and result.returncode == 0 and output.exists() and 0 < output.stat().st_size <= MAX_INLINE_VIDEO_BYTES:
                return output
            try:
                output.unlink(missing_ok=True)
            except OSError:
                pass
        return None
    except OSError:
        try:
            output.unlink(missing_ok=True)
        except OSError:
            pass
        return None


def _video_url(path: Path | None, public_url: str | None) -> tuple[str | None, Path | None]:
    if public_url:
        return public_url, None
    if not path or not path.exists():
        return None, None
    source_path = path
    temporary_preview = None
    if path.stat().st_size > MAX_INLINE_VIDEO_BYTES:
        temporary_preview = _make_model_preview(path)
        if not temporary_preview:
            return None, None
        source_path = temporary_preview
    encoded = base64.b64encode(source_path.read_bytes()).decode("ascii")
    return f"data:video/mp4;base64,{encoded}", temporary_preview


def call_qwen_video(video_path: Path | None, public_url: str | None, goal: str, profile: dict[str, Any]) -> dict[str, Any] | None:
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        return None
    source, temporary_preview = _video_url(video_path, public_url)
    if not source:
        print("qwen_provider: 本地视频超过8MB，请配置公网URL或对象存储", flush=True)
        return None
    endpoint = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    model = os.getenv("QWEN_MODEL", "qwen3-vl-flash")
    system = COMMERCE_SYSTEM_PROMPT if goal == "commerce" else GROWTH_SYSTEM_PROMPT
    if goal == "commerce":
        COMMERCE_USER_INSTRUCTION_WITH_COVER = COMMERCE_USER_INSTRUCTION + "\n请额外输出 cover_analysis：分析封面主体、封面文字、目标人群、点击理由、视觉层级、文字可读性、封面承诺与视频内容是否一致、可复刻等级、改造建议和风险；没有证据写未识别。"
    else:
        COMMERCE_USER_INSTRUCTION_WITH_COVER = COMMERCE_USER_INSTRUCTION
    instruction = COMMERCE_USER_INSTRUCTION if goal == "commerce" else "请输出 summary、duration_seconds、timeline、observations、uncertainties 的合法JSON。"
    if goal == "commerce":
        instruction = instruction + "\n请额外输出 cover_analysis：分析封面主体、封面文字、目标人群、点击理由、视觉层级、文字可读性、封面承诺与视频内容是否一致、可复刻等级、改造建议和风险；没有证据写未识别。"
    user_text = f"{instruction}\n用户账号画像：{json.dumps(profile, ensure_ascii=False)}"
    if goal == "commerce":
        user_text += "\n请按结构化 JSON 返回 cover_analysis，不要只写泛泛的封面评价。"
    payload = {
        "model": model,
        "temperature": 0.1,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": [
            {"type": "video_url", "video_url": {"url": source}},
            {"type": "text", "text": user_text},
        ]}],
    }
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={
        "Authorization": f"Bearer {api_key}", "Content-Type": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=180) as response:
            result = json.loads(response.read().decode("utf-8"))
        content = result["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        parsed = _json_from_content(str(content))
        if parsed:
            return parsed
        print("qwen_provider: 模型返回不是合法JSON", flush=True)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:300]
        print(f"qwen_provider_error: HTTP {error.code} {body}", flush=True)
    except Exception as error:
        print(f"qwen_provider_error: {type(error).__name__}: {error}", flush=True)
    finally:
        if temporary_preview:
            try:
                temporary_preview.unlink(missing_ok=True)
            except OSError:
                pass
    return None

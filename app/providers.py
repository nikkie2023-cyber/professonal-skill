import json
import os
import urllib.error
import urllib.request
from typing import Any

from .prompts import COMMERCE_SYSTEM_PROMPT, COMMERCE_USER_INSTRUCTION


def _extract_json(text: str) -> dict[str, Any] | None:
    text = str(text or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "").strip()
    try:
        result = json.loads(text)
        return result if isinstance(result, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                result = json.loads(text[start:end + 1])
                return result if isinstance(result, dict) else None
            except json.JSONDecodeError:
                pass
    return None


def call_deepseek(report: dict[str, Any]) -> dict[str, Any] | None:
    if os.getenv("USE_DEEPSEEK", "false").lower() != "true" or not os.getenv("DEEPSEEK_API_KEY"):
        return None
    endpoint = os.getenv("DEEPSEEK_BASE_URL", "https://api.deepseek.com/chat/completions")
    model = os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
    system = COMMERCE_SYSTEM_PROMPT
    cover_instruction = "\n请额外输出 cover_analysis：分析封面主体、封面文字、目标人群、点击理由、视觉层级、文字可读性、封面承诺与视频内容是否一致、可复刻等级、改造建议和风险；没有证据写未识别。"
    instruction = COMMERCE_USER_INSTRUCTION + "\n请只输出完整的顶层JSON，不要省略 user_script。"
    evidence = {
        "profile": report.get("user_adaptation", {}).get("profile", {}),
        "video_summary": report.get("video_summary", {}),
        "video_observations": report.get("video_observations", {}),
        "timeline": report.get("timeline", []),
        "frame_assets": report.get("frame_assets", []),
    }
    instruction += cover_instruction
    payload = {"model": model, "temperature": 0.15, "messages": [
        {"role": "system", "content": system},
        {"role": "user", "content": instruction + "\n输入证据：\n" + json.dumps(evidence, ensure_ascii=False)},
    ]}
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={
        "Authorization": f"Bearer {os.getenv('DEEPSEEK_API_KEY')}", "Content-Type": "application/json",
    }, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=120) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        result = _extract_json(content)
        if result:
            return result
        print("deepseek_provider: 模型返回不是合法JSON", flush=True)
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:300]
        print(f"deepseek_provider_error: HTTP {error.code} {body}", flush=True)
    except Exception as error:
        print(f"deepseek_provider_error: {type(error).__name__}: {error}", flush=True)
    return None

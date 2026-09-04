import base64
import html
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any


SCRIPT_SYSTEM = """
你是短视频带货脚本导演。你的任务是把一条已经完成拆解的参考视频，改编成用户自己的商品可执行拍摄方案。
必须保留参考视频中可以复刻的销售结构，但不能照抄原作者的人设、经历、外貌、价格、功效或无法确认的承诺。
只能根据商品图片/商品链接中可以确认的信息写商品内容；无法确认的字段必须写“待用户确认”。
不要承诺爆单，不要虚构使用经历，不要夸大效果，不要编造价格和优惠。
必须只返回合法JSON，不要Markdown。
顶层字段：product_understanding、adaptation_strategy、shots、materials_checklist。
每个shots项必须包含：shot_id、time_range、reference_frame_url、shot_type、camera_angle、composition、visual_scene、visual_evidence、product_appearance、action、voiceover、subtitle、sales_stage、sound_effect、music、editing、materials、compliance_note。
"""


def _json_from_content(content: Any) -> dict[str, Any] | None:
    text = str(content or "").strip()
    if text.startswith("```"):
        text = text.replace("```json", "", 1).replace("```", "").strip()
    try:
        data = json.loads(text)
        return data if isinstance(data, dict) else None
    except json.JSONDecodeError:
        start, end = text.find("{"), text.rfind("}")
        if start >= 0 and end > start:
            try:
                data = json.loads(text[start:end + 1])
                return data if isinstance(data, dict) else None
            except json.JSONDecodeError:
                return None
    return None


def _data_uri(path: Path) -> str | None:
    if not path.exists() or path.stat().st_size > 8 * 1024 * 1024:
        return None
    suffix = path.suffix.lower()
    mime = {".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(suffix, "image/jpeg")
    return f"data:{mime};base64,{base64.b64encode(path.read_bytes()).decode('ascii')}"


def resolve_product_link(url: str) -> tuple[str | None, dict[str, str]]:
    """Return a usable image URL when a product page exposes og:image."""
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("商品链接必须是公开可访问的 http/https 链接")
    meta = {"product_url": url}
    path = parsed.path.lower()
    if any(path.endswith(ext) for ext in (".png", ".jpg", ".jpeg", ".webp")):
        return url, meta
    request = urllib.request.Request(url, headers={"User-Agent": "ContentWorkbenchAgent/0.3"})
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read(2 * 1024 * 1024).decode("utf-8", errors="ignore")
            content_type = response.headers.get("Content-Type", "")
            if content_type.startswith("image/"):
                return url, meta
    except (urllib.error.URLError, urllib.error.HTTPError, TimeoutError):
        return None, meta
    matches = re.findall(r'<meta[^>]+(?:property|name)=["\'](?:og:image|twitter:image)["\'][^>]+content=["\']([^"\']+)', raw, flags=re.I)
    if not matches:
        matches = re.findall(r'<meta[^>]+content=["\']([^"\']+)["\'][^>]+(?:property|name)=["\'](?:og:image|twitter:image)', raw, flags=re.I)
    return (urllib.parse.urljoin(url, html.unescape(matches[0])) if matches else None), meta


def _fallback_script(report: dict[str, Any], product_url: str = "", product_image_url: str = "") -> dict[str, Any]:
    shots = []
    for shot in report.get("shots", []):
        shots.append({
            "shot_id": shot.get("shot_id"), "time_range": shot.get("time_range", "未识别"), "reference_frame_url": shot.get("screenshot_url", ""),
            "shot_type": shot.get("shot_size", "未识别"), "camera_angle": "与参考镜头相同机位，手机固定拍摄", "composition": "主体和商品同时处于画面中心，避免遮挡", "visual_scene": shot.get("replication_advice", shot.get("visual_description", "未识别")), "visual_evidence": "展示商品外观或用户真实可验证的使用证据",
            "product_appearance": "展示用户提供的商品；具体卖点待用户确认", "action": shot.get("product_action", "按参考镜头完成同类动作"),
            "voiceover": "根据商品真实信息补充口播，不要虚构使用体验", "subtitle": shot.get("subtitle_text", "待补充"), "sales_stage": shot.get("sales_stage", "未识别"),
            "sound_effect": "轻微转场或环境音", "music": "低音量背景音乐", "editing": "保留参考镜头节奏，按真实素材剪辑",
            "materials": ["商品实拍图/视频", shot.get("visual_description", "参考画面")], "compliance_note": "商品功效、价格和体验需要用户确认",
        })
    return {"product_understanding": {"product_url": product_url, "visible_information": "待模型识别", "unknown_information": ["价格", "真实功效", "使用体验"]}, "adaptation_strategy": "保留参考视频的销售结构，替换为用户商品的真实画面和可验证卖点。", "shots": shots, "materials_checklist": ["商品正面图", "商品细节图", "用户真实使用或展示画面", "价格/购买信息（如确有）"]}


def generate_product_script(report: dict[str, Any], product_path: Path | None, product_url: str | None) -> dict[str, Any]:
    api_key = os.getenv("QWEN_API_KEY")
    if not api_key:
        raise ValueError("尚未配置千问视觉模型 API Key")
    image_source = _data_uri(product_path) if product_path else None
    link_meta: dict[str, str] = {}
    if product_url:
        image_source, link_meta = resolve_product_link(product_url)
    if not image_source:
        raise ValueError("商品链接没有识别到可读取的商品图片，请粘贴商品图片直链或上传商品图片")
    prompt = {
        "reference_analysis": {"video_summary": report.get("video_summary", {}), "key_nodes": report.get("key_nodes", {}), "shots": report.get("shots", []), "overall_findings": report.get("overall_findings", {})},
        "user_profile": report.get("user_adaptation", {}).get("profile", {}),
        "product_source": link_meta or {"uploaded_image": True},
        "instructions": "参考画面只用于理解结构和构图；每一镜必须写用户实际能拍的画面。商品图片只能证明外观，不能证明功效。",
    }
    endpoint = os.getenv("QWEN_BASE_URL", "https://dashscope.aliyuncs.com/compatible-mode/v1/chat/completions")
    model = os.getenv("QWEN_MODEL", "qwen3-vl-flash")
    payload = {"model": model, "temperature": 0.2, "messages": [{"role": "system", "content": SCRIPT_SYSTEM}, {"role": "user", "content": [{"type": "image_url", "image_url": {"url": image_source}}, {"type": "text", "text": json.dumps(prompt, ensure_ascii=False)}]}]}
    request = urllib.request.Request(endpoint, data=json.dumps(payload, ensure_ascii=False).encode("utf-8"), headers={"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=150) as response:
            raw = json.loads(response.read().decode("utf-8"))
        content = raw["choices"][0]["message"]["content"]
        if isinstance(content, list):
            content = "".join(part.get("text", "") for part in content if isinstance(part, dict))
        result = _json_from_content(content)
        if result:
            if not isinstance(result.get("product_understanding"), dict):
                result["product_understanding"] = {}
            understanding = result["product_understanding"]
            if isinstance(understanding.get("unknown_information"), str):
                understanding["unknown_information"] = [understanding["unknown_information"]]
            if not isinstance(result.get("shots"), list):
                result["shots"] = []
            for shot in result["shots"]:
                if isinstance(shot, dict) and isinstance(shot.get("materials"), str):
                    shot["materials"] = [shot["materials"]]
                if isinstance(shot, dict):
                    shot.setdefault("camera_angle", "手机固定机位，按参考视频方向拍摄")
                    shot.setdefault("composition", "主体与商品同框，保留卖点区域")
                    shot.setdefault("visual_evidence", "只展示视频或商品图片中能够确认的证据")
            if isinstance(result.get("materials_checklist"), str):
                result["materials_checklist"] = [result["materials_checklist"]]
            result["product_image_url"] = product_url or ""
            return result
    except urllib.error.HTTPError as error:
        body = error.read().decode("utf-8", errors="replace")[:240]
        raise ValueError(f"商品图片分析接口返回 HTTP {error.code}: {body}") from error
    except Exception as error:
        raise ValueError(f"商品适配脚本生成失败：{type(error).__name__}") from error
    raise ValueError("模型未返回合法脚本结果，请重试")

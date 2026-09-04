import json
import urllib.request
import urllib.parse
import urllib.error
import shutil
from email.parser import BytesParser
from email.policy import default
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import Any

from .analyzer import analyze_video
from .config import settings
from .excel_export import build_script_xlsx
from .jobs import get_job, start_analysis_job
from .script_generator import generate_product_script
from .storage import FRAME_DIR, UPLOAD_DIR, load_reference, load_report, save_reference, save_report, save_upload

TEMPLATE = Path(__file__).parent / "templates" / "index.html"
EXPORT_SCRIPT = Path(__file__).parent / "static_export.js"
MAX_UPLOAD_BYTES = 200 * 1024 * 1024


def health_payload() -> dict[str, Any]:
    return {"status": "ok", "service": settings.app_name, "environment": settings.app_env, "step": 2}


def parse_multipart(body: bytes, content_type: str) -> dict[str, tuple[str, bytes] | str]:
    message = BytesParser(policy=default).parsebytes((f"Content-Type: {content_type}\r\nMIME-Version: 1.0\r\n\r\n").encode() + body)
    result: dict[str, tuple[str, bytes] | str] = {}
    for part in message.iter_parts():
        disposition = part.get("Content-Disposition", "")
        name = part.get_param("name", header="content-disposition")
        if not name:
            continue
        filename = part.get_filename()
        payload = part.get_payload(decode=True) or b""
        result[name] = (filename or "upload.bin", payload) if filename else payload.decode("utf-8", errors="replace")
    return result


def download_public_video(url: str) -> tuple[str, bytes]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("视频链接必须是公开的 http/https 链接")
    request = urllib.request.Request(url, headers={"User-Agent": "ContentWorkbenchAgent/0.2"})
    try:
        with urllib.request.urlopen(request, timeout=30) as response:
            declared = int(response.headers.get("Content-Length", "0") or 0)
            if declared > MAX_UPLOAD_BYTES:
                raise ValueError("远程视频超过 200MB 限制")
            content = response.read(MAX_UPLOAD_BYTES + 1)
            if len(content) > MAX_UPLOAD_BYTES:
                raise ValueError("远程视频超过 200MB 限制")
            content_type = response.headers.get("Content-Type", "")
    except urllib.error.HTTPError as error:
        raise ValueError(f"服务器无法读取该链接（HTTP {error.code}）。请确认链接公开可访问，或改用上传文件。") from error
    except urllib.error.URLError as error:
        raise ValueError("服务器无法访问该链接。抖音/小红书分享链接可能需要登录或受到平台限制，请改用公开直链或上传文件。") from error
    except TimeoutError as error:
        raise ValueError("读取视频链接超时，请改用上传文件或更换公开直链。") from error
    if not content:
        raise ValueError("远程视频为空")
    if content_type and not content_type.lower().startswith("video/"):
        raise ValueError("当前链接返回的不是视频文件，而是网页或受限页面。请改用公开视频直链，或通过插件保存后上传视频文件。")
    suffix = ".mp4" if "mp4" in content_type.lower() or not Path(parsed.path).suffix else Path(parsed.path).suffix[:8]
    return f"remote_video{suffix}", content


def inspect_public_video_url(url: str) -> dict[str, Any]:
    parsed = urllib.parse.urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        return {"readable": False, "reason": "请提供有效的 http/https 链接"}
    request = urllib.request.Request(url, headers={
        "User-Agent": "ContentWorkbenchAgent/0.2",
        "Range": "bytes=0-1023",
    })
    try:
        with urllib.request.urlopen(request, timeout=10) as response:
            content_type = response.headers.get("Content-Type", "").lower()
            suffix = Path(parsed.path).suffix.lower()
            is_video = content_type.startswith("video/") or suffix in {".mp4", ".mov", ".webm", ".m4v"}
            return {
                "readable": is_video,
                "content_type": content_type,
                "reason": "视频文件可读取" if is_video else "当前链接返回的是网页或受限页面，不是视频文件",
            }
    except Exception as error:
        return {"readable": False, "reason": f"服务器无法访问该链接：{type(error).__name__}"}


class AgentRequestHandler(BaseHTTPRequestHandler):
    server_version = "ContentWorkbenchAgent/0.2"

    def _send(self, status: int, payload: dict[str, Any], content_type: str = "application/json; charset=utf-8") -> None:
        body = json.dumps(payload, ensure_ascii=False).encode("utf-8") if isinstance(payload, dict) else payload
        self.send_response(status); self.send_header("Content-Type", content_type); self.send_header("Access-Control-Allow-Origin", "*"); self.send_header("Access-Control-Allow-Headers", "Content-Type"); self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS"); self.send_header("Content-Length", str(len(body))); self.end_headers(); self.wfile.write(body)

    def do_OPTIONS(self) -> None:  # noqa: N802
        self.send_response(204)
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        self.send_header("Access-Control-Allow-Methods", "GET,POST,OPTIONS")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        if self.path == "/health": self._send(200, health_payload()); return
        if self.path == "/api/status":
            self._send(200, {"ffmpeg": bool(shutil.which("ffmpeg")), "ffprobe": bool(shutil.which("ffprobe")), "qwen_key": bool(__import__("os").getenv("QWEN_API_KEY")), "deepseek_key": bool(__import__("os").getenv("DEEPSEEK_API_KEY"))})
            return
        if self.path.startswith("/api/analyze-status/"):
            job_id = self.path.rsplit("/", 1)[-1].split("?", 1)[0]
            job = get_job(job_id)
            self._send(200, job) if job else self._send(404, {"error": "analysis_job_not_found"})
            return
        if self.path == "/" or self.path.startswith("/?"):
            page = TEMPLATE.read_text(encoding="utf-8").replace("</body>", '<script src="/export.js"></script></body>')
            self._send(200, page.encode("utf-8"), "text/html; charset=utf-8"); return
        if self.path == "/export.js": self._send(200, EXPORT_SCRIPT.read_bytes(), "application/javascript; charset=utf-8"); return
        if self.path.startswith("/api/report/"):
            report = load_report(self.path.rsplit("/", 1)[-1])
            self._send(200, report) if report else self._send(404, {"error": "report_not_found"})
            return
        if self.path.startswith("/api/reference/"):
            reference = load_reference(self.path.rsplit("/", 1)[-1].split("?", 1)[0])
            self._send(200, reference) if reference else self._send(404, {"error": "reference_not_found"})
            return
        if self.path.startswith("/frames/"):
            parts = self.path.split("/")
            if len(parts) == 4:
                frame_path = FRAME_DIR / parts[2] / parts[3]
                if frame_path.exists() and frame_path.is_file():
                    self._send(200, frame_path.read_bytes(), "image/jpeg")
                    return
        if self.path.startswith("/uploads/"):
            parts = self.path.split("/")
            if len(parts) == 4:
                asset_id = parts[2]
                filename = Path(urllib.parse.unquote(parts[3])).name
                upload_path = (UPLOAD_DIR / f"{asset_id}_{filename}").resolve()
                upload_root = UPLOAD_DIR.resolve()
                if upload_path.parent == upload_root and upload_path.exists() and upload_path.is_file():
                    content_type = {".mp4": "video/mp4", ".mov": "video/quicktime", ".png": "image/png", ".jpg": "image/jpeg", ".jpeg": "image/jpeg", ".webp": "image/webp"}.get(upload_path.suffix.lower(), "application/octet-stream")
                    self._send(200, upload_path.read_bytes(), content_type)
                    return
        self._send(404, {"error": "not_found", "path": self.path})

    def do_POST(self) -> None:  # noqa: N802
        if self.path == "/api/check-video-url":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 64 * 1024:
                    raise ValueError("链接检查请求为空或过大")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                self._send(200, inspect_public_video_url(str(payload.get("url", "")).strip()))
            except (ValueError, json.JSONDecodeError) as error:
                self._send(400, {"readable": False, "reason": str(error)})
            return
        if self.path == "/api/import-reference":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 256 * 1024:
                    raise ValueError("导入信息为空或过大")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                url = str(payload.get("url", "")).strip()
                parsed = urllib.parse.urlparse(url)
                if parsed.scheme not in {"http", "https"} or not parsed.netloc:
                    raise ValueError("请提供有效的 http/https 视频页面链接")
                reference = save_reference({
                    "platform": str(payload.get("platform", "unknown"))[:40],
                    "url": url,
                    "title": str(payload.get("title", ""))[:300],
                    "cover_url": str(payload.get("cover_url", ""))[:2000],
                    "author": str(payload.get("author", ""))[:120],
                    "note": str(payload.get("note", ""))[:500],
                    "source": str(payload.get("source", "browser_extension"))[:60],
                })
                self._send(200, {"status": "saved", "reference": reference, "analysis_url": f"/?reference_id={reference['reference_id']}"})
            except (ValueError, json.JSONDecodeError) as error:
                self._send(400, {"error": str(error)})
            return
        if self.path == "/api/export-script":
            try:
                length = int(self.headers.get("Content-Length", "0"))
                if length <= 0 or length > 10 * 1024 * 1024:
                    raise ValueError("导出数据为空或过大")
                payload = json.loads(self.rfile.read(length).decode("utf-8"))
                workbook = build_script_xlsx(payload.get("script", {}), payload.get("report", {}))
                self.send_response(200)
                self.send_header("Content-Type", "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")
                self.send_header("Content-Disposition", 'attachment; filename="content_replication_shooting_pack.xlsx"')
                self.send_header("Content-Length", str(len(workbook)))
                self.end_headers()
                self.wfile.write(workbook)
            except (ValueError, json.JSONDecodeError) as error:
                self._send(400, {"error": str(error)})
            return
        if self.path not in {"/api/analyze", "/api/analyze-async", "/api/import-media", "/api/generate-script"}: self._send(404, {"error": "not_found"}); return
        try:
            length = int(self.headers.get("Content-Length", "0"))
            if length <= 0 or length > MAX_UPLOAD_BYTES: raise ValueError("视频文件为空或超过 200MB 限制")
            content_type = self.headers.get("Content-Type", "")
            if not content_type.startswith("multipart/form-data"): raise ValueError("请使用 multipart/form-data 上传视频")
            fields = parse_multipart(self.rfile.read(length), content_type)
            if self.path == "/api/generate-script":
                report_id = str(fields.get("report_id", "")).strip()
                report = load_report(report_id)
                if not report:
                    raise ValueError("找不到本次拆解报告，请先完成视频拆解")
                uploaded_product = fields.get("product_image")
                product_url = str(fields.get("product_url", "")).strip()
                product_path = None
                if isinstance(uploaded_product, tuple) and uploaded_product[1]:
                    _, product_path = save_upload(uploaded_product[0], uploaded_product[1])
                if not product_path and not product_url:
                    raise ValueError("请上传商品图片，或粘贴商品图片/商品页链接")
                script = generate_product_script(report, product_path, product_url or None)
                script["source_report_id"] = report_id
                script["product_asset_url"] = f"/uploads/{product_path.name.split('_', 1)[0]}/{product_path.name.split('_', 1)[1]}" if product_path else ""
                self._send(200, script)
                return
            uploaded = fields.get("video")
            video_url = str(fields.get("video_url", "")).strip()
            if isinstance(uploaded, tuple) and uploaded[1]:
                filename, content = uploaded
            elif video_url:
                filename, content = download_public_video(video_url)
            else:
                raise ValueError("请上传视频文件或粘贴公开视频链接")
            asset_id, path = save_upload(filename, content)
            goal = str(fields.get("goal", "commerce"))
            profile = {"direction": fields.get("profile_direction", ""), "creator_type": fields.get("profile_creator_type", ""), "goal": fields.get("profile_goal", ""), "notes": fields.get("profile_notes", "")}
            stored_filename = path.name.split("_", 1)[1] if "_" in path.name else path.name
            if self.path == "/api/analyze-async":
                job = start_analysis_job(
                    asset_id, asset_id, path, stored_filename, goal, profile,
                    public_url=video_url or None,
                )
                self._send(202, job)
                return
            report = analyze_video(asset_id, path, stored_filename, goal, profile, public_url=video_url or None)
            if self.path == "/api/import-media":
                report["input_source"] = "browser_capture"
            save_report(report["report_id"], report)
            self._send(200, report)
        except ValueError as error:
            self._send(400, {"error": str(error)})
        except Exception as error:  # keep the API response safe while logging the local cause
            print(f"analysis_error: {type(error).__name__}: {error}", flush=True)
            self._send(500, {"error": "服务器处理失败", "detail": str(error) if settings.app_env == "development" else "请查看服务器日志"})

    def log_message(self, format: str, *args: Any) -> None:
        print(f"{self.address_string()} - {format % args}")


def create_server(port: int | None = None) -> ThreadingHTTPServer:
    return ThreadingHTTPServer((settings.host, settings.port if port is None else port), AgentRequestHandler)


def run() -> None:
    server = create_server(); print(f"{settings.app_name} listening on http://{settings.host}:{settings.port}")
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally: server.server_close()


if __name__ == "__main__": run()

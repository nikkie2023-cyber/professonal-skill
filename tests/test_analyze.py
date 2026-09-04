import http.client
import json
import os
import threading
import unittest
from pathlib import Path

from app.main import create_server


def multipart(fields, file_field, filename, content):
    boundary = "----ContentWorkbenchTest"
    chunks = []
    for name, value in fields.items():
        chunks += [f"--{boundary}\r\n", f'Content-Disposition: form-data; name="{name}"\r\n\r\n', f"{value}\r\n"]
    chunks += [f"--{boundary}\r\n", f'Content-Disposition: form-data; name="{file_field}"; filename="{filename}"\r\n', "Content-Type: video/mp4\r\n\r\n", content, "\r\n", f"--{boundary}--\r\n"]
    body = b""
    for chunk in chunks: body += chunk if isinstance(chunk, bytes) else chunk.encode()
    return f"multipart/form-data; boundary={boundary}", body


class AnalyzeTests(unittest.TestCase):
    def test_import_reference_and_load(self):
        server = create_server(port=0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            payload = json.dumps({"platform": "douyin", "url": "https://www.douyin.com/video/123", "title": "测试视频", "source": "browser_extension"}).encode()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST", "/api/import-reference", body=payload, headers={"Content-Type": "application/json", "Content-Length": str(len(payload))})
            response = conn.getresponse(); data = json.loads(response.read().decode()); conn.close()
            self.assertEqual(response.status, 200); self.assertEqual(data["status"], "saved")
            reference_id = data["reference"]["reference_id"]
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("GET", f"/api/reference/{reference_id}")
            response = conn.getresponse(); loaded = json.loads(response.read().decode()); conn.close()
            self.assertEqual(response.status, 200); self.assertEqual(loaded["url"], "https://www.douyin.com/video/123")
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_import_reference_rejects_invalid_url(self):
        server = create_server(port=0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            payload = json.dumps({"url": "not-a-url"}).encode()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST", "/api/import-reference", body=payload, headers={"Content-Type": "application/json", "Content-Length": str(len(payload))})
            response = conn.getresponse(); response.read(); conn.close()
            self.assertEqual(response.status, 400)
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_upload_generates_mock_report(self):
        old_qwen = os.environ.pop("QWEN_API_KEY", None)
        old_deepseek = os.environ.pop("DEEPSEEK_API_KEY", None)
        old_use = os.environ.pop("USE_DEEPSEEK", None)
        server = create_server(port=0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            ctype, body = multipart({"goal": "commerce", "profile_direction": "穿搭", "profile_creator_type": "普通人真实记录"}, "video", "demo.mp4", b"not-a-real-video-but-valid-upload-bytes")
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST", "/api/analyze", body=body, headers={"Content-Type": ctype, "Content-Length": str(len(body))})
            response = conn.getresponse(); payload = json.loads(response.read().decode())
            self.assertEqual(response.status, 200); self.assertEqual(payload["mode"], "commerce"); self.assertTrue(payload["report_id"])
            self.assertGreaterEqual(len(payload["timeline"]), 3); self.assertTrue(payload["replicable"]); self.assertTrue(payload["non_replicable"])
            self.assertEqual(len(payload["script"]), len(payload["timeline"]))
            self.assertTrue(payload["script"][0]["voiceover"])
            self.assertIn("video_summary", payload)
            self.assertIn("cover_analysis", payload)
            self.assertIn("key_nodes", payload)
            self.assertIn("shots", payload)
            self.assertIn("user_script", payload)
            self.assertTrue(payload["shots"][0]["time_range"])
            self.assertIn(payload["shots"][0]["replication_level"], {"可直接复刻", "改造后复刻", "不建议复刻"})
            self.assertTrue(payload["media_url"].startswith("/uploads/"))
            conn.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)
            if old_qwen is not None: os.environ["QWEN_API_KEY"] = old_qwen
            if old_deepseek is not None: os.environ["DEEPSEEK_API_KEY"] = old_deepseek
            if old_use is not None: os.environ["USE_DEEPSEEK"] = old_use

    def test_invalid_goal_returns_400(self):
        server = create_server(port=0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            ctype, body = multipart({"goal": "unknown"}, "video", "demo.mp4", b"x")
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST", "/api/analyze", body=body, headers={"Content-Type": ctype, "Content-Length": str(len(body))})
            response = conn.getresponse(); self.assertEqual(response.status, 400); conn.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

    def test_generate_script_requires_existing_report(self):
        server = create_server(port=0); thread = threading.Thread(target=server.serve_forever, daemon=True); thread.start()
        try:
            boundary = "----ScriptTest"
            body = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"report_id\"\r\n\r\nmissing\r\n--{boundary}--\r\n").encode()
            conn = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=5)
            conn.request("POST", "/api/generate-script", body=body, headers={"Content-Type": f"multipart/form-data; boundary={boundary}", "Content-Length": str(len(body))})
            response = conn.getresponse(); self.assertEqual(response.status, 400); conn.close()
        finally:
            server.shutdown(); server.server_close(); thread.join(timeout=3)

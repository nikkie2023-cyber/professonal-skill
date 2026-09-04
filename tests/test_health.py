import json
import http.client
import threading
import unittest

from app.main import create_server, health_payload


class HealthTests(unittest.TestCase):
    def test_health_payload_is_stable(self):
        payload = health_payload()
        self.assertEqual(payload["status"], "ok")
        self.assertEqual(payload["step"], 2)
        self.assertTrue(payload["service"])


    def test_health_endpoint_returns_json(self):
        server = create_server(port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            connection.request("GET", "/health")
            response = connection.getresponse()
            self.assertEqual(response.status, 200)
            payload = json.loads(response.read().decode("utf-8"))
            connection.close()
            self.assertEqual(payload["status"], "ok")
            self.assertEqual(payload["step"], 2)
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)


    def test_unknown_route_returns_404(self):
        server = create_server(port=0)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            connection = http.client.HTTPConnection("127.0.0.1", server.server_port, timeout=3)
            try:
                connection.request("GET", "/unknown")
                response = connection.getresponse()
                self.assertEqual(response.status, 404)
            finally:
                connection.close()
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=3)

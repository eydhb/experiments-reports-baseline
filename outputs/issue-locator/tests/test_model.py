"""Exercise the real model HTTP transport against loopback-only stub providers."""

from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
import threading
import unittest
from unittest.mock import patch

from issue_locator.model import ModelClient, ModelError


class ProviderHandler(BaseHTTPRequestHandler):
    def log_message(self, format, *args):
        pass

    def _handle(self):
        raw = self.rfile.read(int(self.headers.get("Content-Length", "0")))
        self.server.requests.append({
            "method": self.command,
            "path": self.path,
            "authorization": self.headers.get("Authorization"),
            "content_type": self.headers.get("Content-Type"),
            "body": raw,
        })
        self.send_response(self.server.response_status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.server.response_body)))
        for name, value in self.server.response_headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(self.server.response_body)

    do_GET = _handle
    do_POST = _handle


class ModelTransportTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.servers = []
        cls.threads = []
        for _ in range(2):
            server = ThreadingHTTPServer(("127.0.0.1", 0), ProviderHandler)
            server.daemon_threads = True
            cls.servers.append(server)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            cls.threads.append(thread)
            thread.start()
        cls.provider, cls.redirect_target = cls.servers

    @classmethod
    def tearDownClass(cls):
        for server in cls.servers:
            server.shutdown()
            server.server_close()
        for thread in cls.threads:
            thread.join(timeout=5)

    def setUp(self):
        for server in self.servers:
            server.requests = []
            server.response_status = 200
            server.response_headers = {}
            server.response_body = json.dumps({
                "choices": [{"message": {"role": "assistant", "content": "ok"}}],
            }).encode("utf-8")
        self.environment = patch.dict("os.environ", {
            "LOCATOR_API_KEY": "synthetic-test-key",
            "LOCATOR_BASE_URL": f"http://127.0.0.1:{self.provider.server_port}/v1",
            "LOCATOR_MODEL": "mock-model",
            "NO_PROXY": "127.0.0.1,localhost",
            "no_proxy": "127.0.0.1,localhost",
        })
        self.environment.start()
        self.addCleanup(self.environment.stop)
        self.client = ModelClient()

    def test_request_sends_expected_route_auth_messages_and_tools(self):
        messages = [{"role": "user", "content": "登录接口返回 500"}]
        tools = [{
            "type": "function",
            "function": {
                "name": "search_code",
                "parameters": {"type": "object", "properties": {
                    "query": {"type": "string"},
                }},
            },
        }]
        reply = self.client.complete(messages, tools)
        self.assertEqual(reply, {"role": "assistant", "content": "ok"})
        self.assertEqual(len(self.provider.requests), 1)
        request = self.provider.requests[0]
        self.assertEqual(request["method"], "POST")
        self.assertEqual(request["path"], "/v1/chat/completions")
        self.assertEqual(request["authorization"], "Bearer synthetic-test-key")
        self.assertEqual(request["content_type"], "application/json")
        payload = json.loads(request["body"])
        self.assertEqual(payload["model"], "mock-model")
        self.assertEqual(payload["messages"], messages)
        self.assertEqual(payload["tools"], tools)
        self.assertEqual(payload["tool_choice"], "auto")

    def test_final_response_request_omits_tool_fields(self):
        self.client.complete([{"role": "user", "content": "Return the final report."}])
        payload = json.loads(self.provider.requests[0]["body"])
        self.assertNotIn("tools", payload)
        self.assertNotIn("tool_choice", payload)

    def test_http_errors_do_not_disclose_provider_body(self):
        self.provider.response_status = 429
        self.provider.response_body = (
            b'{"error":"provider-private-trace synthetic-test-key"}'
        )
        with self.assertRaises(ModelError) as captured:
            self.client.complete([{"role": "user", "content": "login"}])
        message = str(captured.exception)
        self.assertIn("HTTP 429", message)
        self.assertNotIn("provider-private-trace", message)
        self.assertNotIn("synthetic-test-key", message)

    def test_redirects_are_rejected_without_forwarding_credentials(self):
        self.provider.response_headers = {
            "Location": f"http://127.0.0.1:{self.redirect_target.server_port}/capture",
        }
        self.provider.response_body = b"{}"
        for status in (301, 302, 303, 307, 308):
            with self.subTest(status=status):
                self.provider.response_status = status
                with self.assertRaises(ModelError) as captured:
                    self.client.complete([{"role": "user", "content": "login"}])
                self.assertIn(f"HTTP {status}", str(captured.exception))
                self.assertEqual(self.redirect_target.requests, [])
        self.assertEqual(len(self.provider.requests), 5)

    def test_malformed_provider_responses_raise_model_error(self):
        malformed = (
            b"not JSON",
            b'{"choices":[]}',
            b'{"unexpected":"payload"}',
            b'{"choices":[{"message":"not an object"}]}',
        )
        for response in malformed:
            with self.subTest(response=response):
                self.provider.response_body = response
                with self.assertRaises(ModelError):
                    self.client.complete([{"role": "user", "content": "login"}])


if __name__ == "__main__":
    unittest.main()

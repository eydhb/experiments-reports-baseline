"""Loopback HTTP integration tests; public networks are never contacted."""

import http.client
import json
from pathlib import Path
import tempfile
import threading
import unittest
from unittest.mock import patch
from urllib.parse import urlencode

from issue_locator.server import create_server


class ServerTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.temporary = tempfile.TemporaryDirectory()
        cls.server = create_server(data_dir=Path(cls.temporary.name) / "data")
        cls.port = cls.server.server_port
        cls.thread = threading.Thread(target=cls.server.serve_forever, daemon=True)
        cls.thread.start()

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()
        cls.thread.join(timeout=5)
        cls.temporary.cleanup()

    def request(self, method, path, data=None, headers=None, raw=None):
        request_headers = {}
        body = raw
        if data is not None:
            body = json.dumps(data, ensure_ascii=False).encode("utf-8")
        if method == "POST":
            request_headers["Content-Type"] = "application/json"
        request_headers.update(headers or {})
        connection = http.client.HTTPConnection("127.0.0.1", self.port, timeout=15)
        try:
            connection.request(method, path, body=body, headers=request_headers)
            response = connection.getresponse()
            content = response.read()
            response_headers = dict(response.getheaders())
            if "application/json" in response_headers.get("Content-Type", ""):
                content = json.loads(content)
            return response.status, content, response_headers
        finally:
            connection.close()

    def import_sample(self):
        status, body, _ = self.request("POST", "/api/import", {"source": "sample"})
        self.assertEqual(status, 200, body)
        return body["repository"]

    def test_complete_import_analyze_read_flow(self):
        imported = self.import_sample()
        self.assertEqual(imported["source"], "sample")
        self.assertEqual(imported["file_count"], len(imported["files"]))
        self.assertTrue(imported["id"])
        status, result, _ = self.request("POST", "/api/analyze", {
            "repository_id": imported["id"],
            "issue": "登录接口返回 500",
            "mode": "offline",
        })
        self.assertEqual(status, 200, result)
        self.assertEqual(result["engine"], "LangGraph")
        self.assertEqual(result["repository"]["id"], imported["id"])
        self.assertTrue(result["candidates"])
        candidate = result["candidates"][0]
        query = urlencode({
            "repository_id": imported["id"],
            "path": candidate["path"],
            "start_line": candidate["start_line"],
            "end_line": candidate["end_line"],
        })
        status, viewed, _ = self.request("GET", "/api/file?" + query)
        self.assertEqual(status, 200, viewed)
        rows = {row["line"]: row["text"] for row in viewed["lines"]}
        for evidence in candidate["evidence"]:
            self.assertEqual(rows[evidence["line"]], evidence["text"])

    def test_status_does_not_expose_credentials(self):
        secret = "test-secret-that-must-never-appear"
        with patch.dict("os.environ", {
            "LOCATOR_API_KEY": secret,
            "LOCATOR_BASE_URL": "https://example.invalid/v1",
            "LOCATOR_MODEL": "test-model",
        }):
            status, body, headers = self.request("GET", "/api/status")
        self.assertEqual(status, 200)
        self.assertTrue(body["model_available"])
        self.assertEqual(body["engine"], "LangGraph")
        self.assertNotIn(secret, json.dumps(body))
        self.assertNotIn("LOCATOR_API_KEY", json.dumps(body))
        self.assertEqual(headers["Cache-Control"], "no-store")
        self.assertEqual(headers["X-Content-Type-Options"], "nosniff")
        self.assertIn("frame-ancestors 'none'", headers["Content-Security-Policy"])

    def test_foreign_hosts_and_origins_cannot_access_repository_api(self):
        for headers in (
            {"Host": "attacker.invalid"},
            {"Host": f"attacker.invalid:{self.port}"},
            {"Origin": "https://attacker.invalid"},
            {"Origin": "null"},
            {"Sec-Fetch-Site": "cross-site"},
        ):
            with self.subTest(headers=headers):
                status, body, _ = self.request("GET", "/api/status", headers=headers)
                self.assertEqual(status, 403, body)
                status, body, _ = self.request(
                    "POST", "/api/import", {"source": "sample"}, headers=headers,
                )
                self.assertEqual(status, 403, body)
        status, body, _ = self.request("GET", "/api/status", headers={
            "Origin": f"http://127.0.0.1:{self.port}",
        })
        self.assertEqual(status, 200, body)

    def test_listener_cannot_bind_public_interfaces(self):
        with self.assertRaises(ValueError):
            create_server(host="0.0.0.0", data_dir=self.temporary.name)

    def test_file_reads_reject_traversal_and_excluded_paths(self):
        imported = self.import_sample()
        for path in (
            "../outside.txt", "..\\outside.txt", "/etc/passwd",
            "C:\\Windows\\win.ini", ".git/config", ".env", "README.md:secret",
        ):
            with self.subTest(path=path):
                query = urlencode({"repository_id": imported["id"], "path": path})
                status, body, _ = self.request("GET", "/api/file?" + query)
                self.assertEqual(status, 400, body)
                self.assertIn("error", body)

    def test_invalid_line_ranges_return_errors(self):
        imported = self.import_sample()
        for start, end in ((0, 10), (10, 2), (1, 1000), ("nan", 5)):
            with self.subTest(start=start, end=end):
                query = urlencode({
                    "repository_id": imported["id"], "path": "README.md",
                    "start_line": start, "end_line": end,
                })
                status, body, _ = self.request("GET", "/api/file?" + query)
                self.assertEqual(status, 400, body)
                self.assertIn("error", body)

    def test_unknown_repository_returns_not_found(self):
        status, body, _ = self.request("POST", "/api/analyze", {
            "repository_id": "does-not-exist", "issue": "login",
        })
        self.assertEqual(status, 404, body)
        status, body, _ = self.request("GET", "/api/file?" + urlencode({
            "repository_id": "does-not-exist", "path": "README.md",
        }))
        self.assertEqual(status, 404, body)

    def test_malformed_requests_are_rejected(self):
        for raw in (b"{", b"[]", b"null", b'"\xff"', b""):
            with self.subTest(raw=raw):
                status, body, _ = self.request("POST", "/api/import", raw=raw)
                self.assertEqual(status, 400, body)
                self.assertIn("error", body)
        status, body, _ = self.request(
            "POST", "/api/import", raw=b'{"source":"sample"}',
            headers={"Content-Type": "text/plain"},
        )
        self.assertEqual(status, 400, body)
        status, body, _ = self.request(
            "POST", "/api/import", raw=b"x" * 32001,
        )
        self.assertEqual(status, 400, body)

    def test_local_import_reads_source_without_executing_it(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            marker = root / "executed.txt"
            (root / "main.py").write_text(
                "from pathlib import Path\n"
                f"Path({str(marker)!r}).write_text('must not run')\n"
                "def login():\n    return 500\n",
                encoding="utf-8",
            )
            status, body, _ = self.request("POST", "/api/import", {
                "source": "local", "path": str(root),
            })
            self.assertEqual(status, 200, body)
            status, result, _ = self.request("POST", "/api/analyze", {
                "repository_id": body["repository"]["id"], "issue": "login",
                "mode": "offline",
            })
            self.assertEqual(status, 200, result)
            self.assertFalse(marker.exists())
            self.assertTrue(result["candidates"])

    def test_invalid_github_urls_do_not_start_git(self):
        invalid = (
            "http://github.com/owner/repo",
            "https://github.com.evil.invalid/owner/repo",
            "https://example.invalid/owner/repo",
            "https://github.com/owner/repo/tree/main",
            "https://github.com/owner/repo?token=secret",
            "file:///tmp/repo",
            "--upload-pack=evil",
        )
        with patch("issue_locator.server.subprocess.run") as run:
            for url in invalid:
                with self.subTest(url=url):
                    status, body, _ = self.request("POST", "/api/import", {
                        "source": "github", "url": url,
                    })
                    self.assertEqual(status, 400, body)
            run.assert_not_called()

    def test_unconfigured_model_returns_actionable_error(self):
        imported = self.import_sample()
        with patch.dict("os.environ", {
            "LOCATOR_API_KEY": "", "LOCATOR_BASE_URL": "", "LOCATOR_MODEL": "",
        }):
            status, body, _ = self.request("POST", "/api/analyze", {
                "repository_id": imported["id"], "issue": "login", "mode": "model",
            })
        self.assertEqual(status, 400, body)
        self.assertIn("模型未配置", body["error"])


if __name__ == "__main__":
    unittest.main()

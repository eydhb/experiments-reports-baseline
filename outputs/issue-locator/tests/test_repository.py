from __future__ import annotations

import hashlib
from pathlib import Path
import tempfile
import unittest

from issue_locator.repository import Repository


class RepositoryTests(unittest.TestCase):
    def setUp(self):
        self.directory = tempfile.TemporaryDirectory()
        self.addCleanup(self.directory.cleanup)
        self.root = Path(self.directory.name)

    def write(self, relative, text):
        path = self.root / relative
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")
        return path

    def test_search_and_read_preserve_real_lines(self):
        source = "package demo;\n\npublic void LOGIN() {}\n// 中文：登录\n"
        path = self.write("src/UserController.java", source)
        repo = Repository(self.root)
        search = repo.search_code("login")
        self.assertEqual(search["matches"], [{
            "path": "src/UserController.java", "line": 3,
            "snippet": "public void LOGIN() {}",
        }])
        read = repo.read_file("src/UserController.java", 2, 4)
        self.assertEqual(read["lines"], [
            {"line": 2, "text": ""},
            {"line": 3, "text": "public void LOGIN() {}"},
            {"line": 4, "text": "// 中文：登录"},
        ])
        self.assertEqual(read["end_line"], 4)
        self.assertEqual(read["sha256"], hashlib.sha256(path.read_bytes()).hexdigest())
        self.assertEqual(repo.search_code("登录")["matches"][0]["line"], 4)

    def test_ignored_directories_and_secrets_cannot_be_read(self):
        for relative in [
            ".git/config.py", "node_modules/a/index.js", "target/compiled.java",
            ".venv/site.py", ".aws/config.json", ".env", ".env.local",
            ".env.example", "private.pem", "private.key", "credentials.json",
            ".env.production/config.py",
        ]:
            self.write(relative, "login = secret")
        self.write("src/safe.py", "login = 'allowed'")
        repo = Repository(self.root)
        self.assertEqual(repo.list_files()["files"], ["src/safe.py"])
        self.assertEqual(len(repo.search_code("login")["matches"]), 1)
        for relative in [".env.local", "credentials.json", ".git/config.py",
                         ".env.production/config.py"]:
            with self.assertRaises(ValueError):
                repo.read_file(relative)

    def test_traversal_and_absolute_paths_are_rejected(self):
        self.write("good.py", "hello")
        repo = Repository(self.root)
        for relative in [".", "../good.py", "..\\good.py", "/etc/passwd", "C:\\file.py",
                         "good.py:stream", "folder/../../good.py"]:
            with self.assertRaises(ValueError, msg=relative):
                repo.read_file(relative)

    def test_search_is_literal_and_reports_truncation(self):
        self.write("b.py", "login\nlogin\n")
        self.write("a.py", "login(.*)\n")
        result = Repository(self.root).search_code("login", limit=2)
        self.assertEqual([(m["path"], m["line"]) for m in result["matches"]],
                         [("a.py", 1), ("b.py", 1)])
        self.assertTrue(result["truncated"])
        literal = Repository(self.root).search_code("(.*)")
        self.assertEqual(len(literal["matches"]), 1)
        self.assertFalse(literal["truncated"])

    def test_file_count_size_and_binary_bounds(self):
        self.write("a.py", "login")
        self.write("b.py", "login")
        limited = Repository(self.root)
        limited.MAX_FILES = 1
        self.assertEqual(limited.list_files()["files"], ["a.py"])
        self.assertTrue(limited.list_files()["truncated"])
        size_limited = Repository(self.root)
        size_limited.MAX_FILE_BYTES = 3
        self.assertEqual(size_limited.list_files()["files"], [])
        self.assertTrue(size_limited.list_files()["truncated"])
        with self.assertRaises(ValueError):
            size_limited.read_file("a.py")
        self.write("binary.py", "hello\x00login")
        self.assertNotIn("binary.py", [
            item["path"] for item in Repository(self.root).search_code("login")["matches"]
        ])

    def test_invalid_ranges_and_queries(self):
        self.write("test.py", "one\ntwo\n")
        repo = Repository(self.root)
        for start, end in [(0, 2), (3, 2), (1, 401), (True, 2), (3, 4)]:
            with self.assertRaises(ValueError):
                repo.read_file("test.py", start, end)
        for query in ["", "  ", "a\nb", "x" * 257]:
            with self.assertRaises(ValueError):
                repo.search_code(query)
        for limit in [0, 201, True]:
            with self.assertRaises(ValueError):
                repo.search_code("one", limit)

    def test_symlinks_cannot_escape_or_be_read_directly(self):
        self.write("actual.py", "login")
        link = self.root / "link.py"
        try:
            link.symlink_to(self.root / "actual.py")
        except (OSError, NotImplementedError):
            self.skipTest("This Windows account cannot create symlinks")
        repo = Repository(self.root)
        self.assertEqual(repo.list_files()["files"], ["actual.py"])
        with self.assertRaises(ValueError):
            repo.read_file("link.py")


if __name__ == "__main__":
    unittest.main()

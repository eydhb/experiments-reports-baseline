"""Behavioral checks for the graph and source-backed candidate citations."""

import json
from pathlib import Path
import tempfile
import unittest

from issue_locator.agent import analyze
from issue_locator.model import ModelError
from issue_locator.repository import Repository


PROJECT = Path(__file__).resolve().parents[1]
SAMPLE = PROJECT / "sample_repo"


def tool_call(name, arguments, call_id="call_1"):
    return {
        "content": None,
        "tool_calls": [{
            "id": call_id,
            "type": "function",
            "function": {"name": name, "arguments": json.dumps(arguments)},
        }],
    }


class ScriptedModel:
    """A local protocol fake; no model account or network is required."""

    available = True

    def __init__(self, responses):
        self.responses = iter(responses)
        self.calls = []

    def complete(self, messages, tools=None):
        self.calls.append({"messages": list(messages), "tools": tools})
        response = next(self.responses)
        return response() if callable(response) else response


class AgentTests(unittest.TestCase):
    def test_login_query_follows_sample_chain_and_cites_actual_source(self):
        result = analyze(Repository(SAMPLE), "登录接口返回 500")
        self.assertEqual(result["engine"], "LangGraph")
        self.assertEqual(result["mode"], "offline")
        self.assertGreaterEqual(result["elapsed_ms"], 0)
        names = {Path(item["path"]).name for item in result["candidates"]}
        self.assertTrue({
            "UserController.java", "UserService.java", "TokenService.java",
            "GlobalExceptionHandler.java",
        }.issubset(names), names)
        self.assertNotIn("HealthController.java", names)
        self.assertTrue(result["pending"])
        self.assertIn("尚未确认", result["summary"])
        self.assertTrue(any("规则检索" in value for value in result["warnings"]))
        tools = {entry["tool"] for entry in result["trace"]}
        self.assertTrue({"list_repo_files", "search_code", "read_file"}.issubset(tools))
        for candidate in result["candidates"]:
            with self.subTest(path=candidate["path"]):
                source = (SAMPLE / candidate["path"]).read_text(encoding="utf-8").splitlines()
                self.assertGreaterEqual(candidate["start_line"], 1)
                self.assertLessEqual(candidate["end_line"], len(source))
                self.assertTrue(candidate["reason"])
                self.assertTrue(candidate["pending"])
                self.assertTrue(candidate["evidence"])
                for row in candidate["evidence"]:
                    self.assertGreaterEqual(row["line"], candidate["start_line"])
                    self.assertLessEqual(row["line"], candidate["end_line"])
                    self.assertEqual(row["text"], source[row["line"] - 1])

    def test_unrelated_query_does_not_invent_candidates(self):
        result = analyze(Repository(SAMPLE), "量子卫星姿态校准失败")
        self.assertEqual(result["candidates"], [])
        self.assertIn("未找到", result["summary"])
        self.assertTrue(result["pending"])

    def test_invalid_issue_and_mode_fail_before_analysis(self):
        repository = Repository(SAMPLE)
        for issue in ("", " \t\n", None, ["login"], "a" * 8001):
            with self.subTest(issue=repr(issue)[:40]):
                with self.assertRaises(ValueError):
                    analyze(repository, issue)
        for mode in ("unknown", [], {}, None):
            with self.subTest(mode=mode):
                with self.assertRaises(ValueError):
                    analyze(repository, "login", mode=mode)

    def test_model_citations_use_tools_and_discard_unread_files(self):
        relative = "src/main/java/demo/auth/controller/UserController.java"
        model = ScriptedModel([
            tool_call("read_file", {"path": relative, "start_line": 20, "end_line": 23}),
            {"content": json.dumps({
                "summary": "需要结合日志验证认证调用。",
                "candidates": [
                    {"path": relative, "start_line": 20, "end_line": 23,
                     "reason": "登录入口调用认证服务。", "pending": ["核对异常堆栈。"],
                     "evidence": [{"line": 20, "text": "fabricated source"}]},
                    {"path": "invented/Missing.java", "start_line": 1, "end_line": 3,
                     "reason": "Unsupported claim"},
                ],
                "pending": ["需要请求日志。"],
            })},
        ])
        result = analyze(Repository(SAMPLE), "登录接口返回 500", "model", model)
        self.assertEqual(len(result["candidates"]), 1)
        candidate = result["candidates"][0]
        self.assertEqual(candidate["path"], relative)
        source = (SAMPLE / relative).read_text(encoding="utf-8").splitlines()
        self.assertEqual(
            candidate["evidence"],
            [{"line": number, "text": source[number - 1]} for number in range(20, 24)],
        )
        self.assertTrue(any("未读" in value for value in result["warnings"]))
        self.assertTrue(any(
            message["role"] == "tool"
            for message in model.calls[-1]["messages"]
        ))

    def test_model_cannot_cite_unread_gap_between_two_windows(self):
        relative = "src/main/java/demo/auth/controller/UserController.java"
        model = ScriptedModel([
            tool_call("read_file", {"path": relative, "start_line": 12, "end_line": 13}, "a"),
            tool_call("read_file", {"path": relative, "start_line": 20, "end_line": 23}, "b"),
            {"content": json.dumps({
                "candidates": [{"path": relative, "start_line": 12, "end_line": 23,
                                "reason": "The intervening lines were not read."}],
            })},
        ])
        result = analyze(Repository(SAMPLE), "login", "model", model)
        self.assertEqual(result["candidates"], [])
        self.assertTrue(result["warnings"])

    def test_model_bad_tool_path_is_reported_without_reading_outside_repository(self):
        model = ScriptedModel([
            tool_call("read_file", {"path": "../outside.txt", "start_line": 1, "end_line": 2}),
            {"content": '{"candidates":[]}'},
        ])
        result = analyze(Repository(SAMPLE), "login", "model", model)
        self.assertEqual(result["candidates"], [])
        tool_messages = [
            message for message in model.calls[-1]["messages"]
            if message["role"] == "tool"
        ]
        self.assertEqual(len(tool_messages), 1)
        self.assertIn("error", json.loads(tool_messages[0]["content"]))

    def test_changed_file_citation_is_removed(self):
        with tempfile.TemporaryDirectory() as directory:
            path = Path(directory) / "auth.py"
            path.write_text("def login():\n    return authenticate()\n", encoding="utf-8")

            def change_before_reporting():
                path.write_text("def login():\n    return None\n", encoding="utf-8")
                return {"content": json.dumps({
                    "candidates": [{"path": "auth.py", "start_line": 1, "end_line": 2,
                                    "reason": "Old read should not survive a source edit."}],
                })}

            model = ScriptedModel([
                tool_call("read_file", {"path": "auth.py", "start_line": 1, "end_line": 2}),
                change_before_reporting,
            ])
            result = analyze(Repository(directory), "login", "model", model)
            self.assertEqual(result["candidates"], [])
            self.assertTrue(any("变化" in warning for warning in result["warnings"]))

    def test_invalid_model_json_gives_actionable_error(self):
        for content in ("not valid JSON", {"unexpected": True}, ["unexpected"]):
            with self.subTest(content=content):
                model = ScriptedModel([{"content": content}])
                with self.assertRaises(ModelError):
                    analyze(Repository(SAMPLE), "login", "model", model)


if __name__ == "__main__":
    unittest.main()

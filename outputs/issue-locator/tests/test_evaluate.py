import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from issue_locator.evaluate import evaluate


CASE = {"case_id": "synthetic-test", "issue_url": "synthetic://test",
        "base_commit": "before", "fix_commit": "after",
        "expected_files": ["src/auth.py", "src/token.py"]}


def result(*paths):
    return {"mode": "offline", "candidates": [{"path": p} for p in paths]}


class EvaluationTests(unittest.TestCase):
    def test_first_hit_and_partial_recall(self):
        report = evaluate(result("src/auth.py", "other.py"), CASE)
        self.assertEqual(report["metrics"], {
            "top_1_hit": True, "top_3_hit": True, "first_relevant_rank": 1,
            "reciprocal_rank": 1.0, "file_recall": 0.5})
        self.assertEqual(report["missed_files"], ["src/token.py"])

    def test_top_three_boundary(self):
        for rank in (2, 3, 4):
            metrics = evaluate(result(*([f"x{i}.py" for i in range(rank - 1)] + ["src/auth.py"])), CASE)["metrics"]
            self.assertFalse(metrics["top_1_hit"])
            self.assertEqual(metrics["top_3_hit"], rank <= 3)
            self.assertEqual(metrics["reciprocal_rank"], 1 / rank)

    def test_empty_and_wrong_directory_are_misses(self):
        for paths in ((), ("auth.py", "other/auth.py", "src/Auth.py")):
            metrics = evaluate(result(*paths), CASE)["metrics"]
            self.assertIsNone(metrics["first_relevant_rank"])
            self.assertFalse(metrics["top_3_hit"])
            self.assertEqual(metrics["file_recall"], 0)

    def test_normalization_and_deduplication_preserve_order(self):
        report = evaluate(result("./other.py", "other.py", "src\\auth.py", "src/token.py"),
                          {**CASE, "expected_files": ["./src/auth.py", "src/auth.py", "src/token.py"]})
        self.assertEqual(report["metrics"]["first_relevant_rank"], 2)
        self.assertEqual(report["metrics"]["file_recall"], 1)

    def test_invalid_labels_and_results_fail(self):
        for labels in ([], None, "src/auth.py", ["../x"], ["/x"], ["C:\\x"], ["."], [None]):
            with self.subTest(labels=labels), self.assertRaises(ValueError):
                evaluate(result(), {**CASE, "expected_files": labels})
        for invalid in ({}, {"candidates": None}, {"candidates": [None]}, result("../x")):
            with self.subTest(invalid=invalid), self.assertRaises(ValueError):
                evaluate(invalid, CASE)
        with self.assertRaises(ValueError):
            evaluate(result(), {**CASE, "base_commit": ""})

    def test_cli_artifact_hashes_and_input_protection(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source, case, output = [root / name for name in ("result.json", "case.json", "evaluation.json")]
            source.write_text(json.dumps(result("src/auth.py")), encoding="utf-8")
            case.write_text(json.dumps(CASE), encoding="utf-8")
            command = [sys.executable, "-m", "issue_locator.evaluate", "--result", str(source), "--case", str(case), "--output"]
            run = subprocess.run(command + [str(output)], capture_output=True, text=True)
            self.assertEqual(run.returncode, 0, run.stderr)
            report = json.loads(output.read_text(encoding="utf-8"))
            self.assertEqual(report["inputs_sha256"]["result"], hashlib.sha256(source.read_bytes()).hexdigest())
            original = source.read_bytes()
            run = subprocess.run(command + [str(source)], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertEqual(source.read_bytes(), original)
            source.write_text("broken json", encoding="utf-8")
            run = subprocess.run(command + [str(output)], capture_output=True, text=True)
            self.assertNotEqual(run.returncode, 0)
            self.assertNotIn("Traceback", run.stderr)


if __name__ == "__main__":
    unittest.main()

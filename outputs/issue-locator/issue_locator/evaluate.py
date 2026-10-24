"""Score saved localization results without exposing fix labels to the agent."""

import argparse
import hashlib
import json
from pathlib import Path
import re


def normalize_path(value):
    """Compare repository-relative paths, preserving case and directory names."""
    if not isinstance(value, str) or not value.strip():
        raise ValueError("File paths must be non-empty strings")
    value = value.replace("\\", "/")
    if value.startswith("/") or re.match(r"^[A-Za-z]:", value):
        raise ValueError("File paths must be repository-relative")
    parts = value.split("/")
    if ".." in parts:
        raise ValueError("File paths must not contain '..'")
    normalized = "/".join(p for p in parts if p and p != ".")
    if not normalized:
        raise ValueError("File paths must name a file")
    return normalized


def evaluate(result, case):
    """Top-k means any labeled file appears among the first k unique files.

    Labels and commit identifiers are supplied by the evaluator, not verified
    against Git. File hits do not establish correct line or root-cause diagnosis.
    """
    if not isinstance(result, dict) or not isinstance(result.get("candidates"), list):
        raise ValueError("Result must contain a candidates array")
    if not isinstance(case, dict):
        raise ValueError("Case must be an object")
    for key in ("case_id", "issue_url", "base_commit", "fix_commit"):
        if not isinstance(case.get(key), str) or not case[key].strip():
            raise ValueError(f"Case requires a non-empty {key}")
    labels = case.get("expected_files")
    if not isinstance(labels, list) or not labels:
        raise ValueError("Case requires a non-empty expected_files array")
    expected = list(dict.fromkeys(normalize_path(p) for p in labels))
    ranked = []
    for candidate in result["candidates"]:
        if not isinstance(candidate, dict):
            raise ValueError("Each candidate must be an object with a path")
        path = normalize_path(candidate.get("path"))
        if path not in ranked:
            ranked.append(path)
    matched = [p for p in ranked if p in expected]
    first = ranked.index(matched[0]) + 1 if matched else None
    return {
        "schema_version": 1,
        "case": {**{k: case[k] for k in ("case_id", "issue_url", "base_commit", "fix_commit")},
                 "expected_files": expected},
        "mode": result.get("mode"),
        "ranked_files": ranked,
        "matched_files": matched,
        "missed_files": [p for p in expected if p not in ranked],
        "metrics": {"top_1_hit": first == 1,
                    "top_3_hit": first is not None and first <= 3,
                    "first_relevant_rank": first,
                    "reciprocal_rank": 1 / first if first else 0.0,
                    "file_recall": len(matched) / len(expected)},
        "limitations": [
            "File-level evaluation only; line accuracy and root cause are not scored.",
            "Commit metadata and labels are user-supplied, not independently verified.",
        ],
    }


def main(argv=None):
    parser = argparse.ArgumentParser(description="Evaluate an exported CodeLens result")
    parser.add_argument("--result", required=True, type=Path)
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--output", required=True, type=Path)
    args = parser.parse_args(argv)
    try:
        if args.output.resolve() in (args.result.resolve(), args.case.resolve()):
            raise ValueError("Output must not overwrite either input")
        result_bytes = args.result.read_bytes()
        case_bytes = args.case.read_bytes()
        report = evaluate(json.loads(result_bytes), json.loads(case_bytes))
        report["inputs_sha256"] = {
            "result": hashlib.sha256(result_bytes).hexdigest(),
            "case": hashlib.sha256(case_bytes).hexdigest(),
        }
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(1, f"Evaluation failed: {exc}\n")
    print(json.dumps(report["metrics"], ensure_ascii=False))


if __name__ == "__main__":
    main()

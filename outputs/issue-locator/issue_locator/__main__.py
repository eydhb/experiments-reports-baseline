import argparse
import json
from pathlib import Path

from .agent import analyze
from .repository import Repository


def main():
    parser = argparse.ArgumentParser(description="从问题描述定位代码候选文件")
    parser.add_argument("--repo", default=str(Path(__file__).resolve().parent.parent / "sample_repo"))
    parser.add_argument("--issue", default="登录接口返回 500")
    parser.add_argument("--mode", choices=["offline", "model"], default="offline")
    parser.add_argument("--output", help="把结果 JSON 保存到指定文件")
    args = parser.parse_args()
    try:
        result = analyze(Repository(args.repo), args.issue, args.mode)
    except (ValueError, OSError) as exc:
        parser.exit(1, str(exc) + "\n")
    text = json.dumps(result, ensure_ascii=False, indent=2)
    if args.output:
        Path(args.output).write_text(text + "\n", encoding="utf-8")
    print(text)


if __name__ == "__main__":
    main()

"""Replay a pinned case (Click #3802 by default); fix labels never enter the agent.

Run from outputs/issue-locator with the project Python. Prepare a clean checkout
of the pinned base commit, then pass --repo. Outputs default to an ignored data
directory to preserve the original experiment artifacts.
"""

import argparse
from datetime import datetime, timezone
import hashlib
from importlib.metadata import version
import json
from pathlib import Path
import platform
import sys

APP = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(APP))

from issue_locator.agent import analyze, issue_queries, MAX_READS, MAX_STEPS
from issue_locator.repository import Repository


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


class RecordedRepository(Repository):
    """Record unchanged tool responses, including search truncation and reads."""

    def __init__(self, root):
        super().__init__(root)
        self.tool_results = []

    def search_code(self, query, **kwargs):
        result = super().search_code(query, **kwargs)
        self.tool_results.append({'tool': 'search_code', 'query': query, 'result': result})
        return result

    def read_file(self, path, start_line=1, end_line=80):
        result = super().read_file(path, start_line, end_line)
        self.tool_results.append({'tool': 'read_file', 'result': result})
        return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--repo', type=Path, required=True)
    parser.add_argument('--case-dir', type=Path, default=APP / 'experiments/real_issue_001',
                        help='Directory containing issue.txt and source-manifest.json')
    parser.add_argument('--output-dir', type=Path, default=APP / 'data/real_issue_001/replay')
    args = parser.parse_args()
    original = args.case_dir
    provenance = json.loads((original / 'source-manifest.json').read_text(encoding='utf-8'))

    def verify_source():
        for path, expected in provenance['source_sha256'].items():
            if digest(args.repo / path) != expected:
                raise ValueError(f'Source does not match pinned base commit: {path}')
        # Ignore Git metadata only. Additional source/data can affect retrieval.
        actual = {p.relative_to(args.repo).as_posix() for p in args.repo.rglob('*')
                  if p.is_file() and '.git' not in p.relative_to(args.repo).parts}
        if actual != set(provenance['source_sha256']):
            raise ValueError('Source tree contains missing or extra files')

    verify_source()
    output = args.output_dir
    output.mkdir(parents=True, exist_ok=True)
    for name in ('result.json', 'tool-results.json', 'run.json'):
        if (output / name).exists():
            raise ValueError(f'Refusing to overwrite {output / name}; choose a new output directory')
    issue = (original / 'issue.txt').read_text(encoding='utf-8').strip()
    repo = RecordedRepository(args.repo)
    result = analyze(repo, issue, mode='offline')
    verify_source()
    for candidate in result['candidates']:
        lines = (args.repo / candidate['path']).read_text(encoding='utf-8-sig').splitlines()
        for row in candidate['evidence']:
            assert lines[row['line']-1] == row['text']
    run = {
        'run_at_utc': datetime.now(timezone.utc).isoformat(),
        'case_id': original.name, 'base_commit': provenance['base_commit'],
        'mode': 'offline', 'model': None, 'python': platform.python_version(),
        'platform': platform.platform(), 'langgraph': version('langgraph'),
        'max_steps': MAX_STEPS, 'max_reads': MAX_READS,
        'initial_queries': issue_queries(issue),
        'issue_txt_sha256': digest(original / 'issue.txt'),
        'locator_sha256': {p.name: digest(p) for p in sorted((APP / 'issue_locator').glob('*.py'))},
        'source_verified_before_and_after': True, 'all_candidate_evidence_verified': True,
        'repository_file_list': repo.list_files(),
        'fix_metadata_passed_to_agent': False,
    }
    for name, value in [('result.json',result), ('tool-results.json',repo.tool_results), ('run.json',run)]:
        (output / name).write_text(json.dumps(value, ensure_ascii=False, indent=2)+'\n', encoding='utf-8')
    print(json.dumps({'candidates':[c['path'] for c in result['candidates']],
                      'steps':len(result['trace']), 'queries':run['initial_queries']}, ensure_ascii=False))


if __name__ == '__main__':
    main()

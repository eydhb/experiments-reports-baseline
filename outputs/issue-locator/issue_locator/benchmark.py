"""Deterministic, offline file-hit evaluation of saved CodeLens outputs."""

import argparse
import hashlib
import json
from pathlib import Path
import re

from .evaluate import evaluate


def _read(path):
    raw = path.read_bytes()
    return json.loads(raw), hashlib.sha256(raw).hexdigest()


def _resolve(root, relative, base=None):
    if not isinstance(relative, str) or not relative or Path(relative).is_absolute():
        raise ValueError('Input paths must be non-empty relative paths')
    path = ((base or root) / relative).resolve()
    if not path.is_relative_to(root):
        raise ValueError(f'Input path escapes the suite directory: {relative}')
    return path


def evaluate_suite(manifest_path):
    """Validate every case and score all or fail; never silently skip a case."""
    manifest_path = Path(manifest_path).resolve()
    root = manifest_path.parent
    manifest, manifest_hash = _read(manifest_path)
    if not isinstance(manifest, dict) or manifest.get('schema_version') != 1:
        raise ValueError('Manifest requires schema_version 1')
    entries = manifest.get('cases')
    if not isinstance(entries, list) or not entries:
        raise ValueError('Manifest requires a non-empty cases list')
    cases, seen_ids, seen_issues, seen_results = [], set(), set(), set()
    for entry in entries:
        case_path = _resolve(root, entry)
        case, case_hash = _read(case_path)
        if not isinstance(case, dict):
            raise ValueError(f'Case must be an object: {entry}')
        # Evaluate validates IDs, labels and candidate paths. Here require real
        # issue coordinates and immutable versions for the experiment manifest.
        url = case.get('issue_url', '')
        match = re.fullmatch(r'https://github\.com/([^/]+/[^/]+)/issues/([1-9][0-9]*)', url) if isinstance(url, str) else None
        number = case.get('issue_number')
        if not match or type(number) is not int or number != int(match[2]):
            raise ValueError(f'Issue URL and issue_number must agree: {entry}')
        for key in ('base_commit', 'fix_commit'):
            if not isinstance(case.get(key), str) or not re.fullmatch('[0-9a-f]{40}', case[key]):
                raise ValueError(f'Case requires a full lowercase {key} SHA: {entry}')
        result_path = _resolve(root, case.get('result_path'), case_path.parent)
        result, result_hash = _read(result_path)
        if result_hash != case.get('result_sha256'):
            raise ValueError(f'Saved result SHA-256 mismatch: {entry}')
        score = evaluate(result, case)
        case_id = case['case_id']
        identity = (match[1].casefold(), number)
        if case_id in seen_ids or identity in seen_issues or result_path in seen_results:
            raise ValueError(f'Duplicate case, issue or result: {entry}')
        seen_ids.add(case_id)
        seen_issues.add(identity)
        seen_results.add(result_path)
        analysis = case.get('failure_analysis', {
            'status': 'pending', 'categories': [], 'reason': 'Pending manual analysis.'})
        if (not isinstance(analysis, dict)
                or analysis.get('status') not in ('analyzed', 'pending')
                or not isinstance(analysis.get('reason'), str) or not analysis['reason'].strip()
                or not isinstance(analysis.get('categories'), list)
                or any(c not in ('retrieval', 'ranking', 'root_cause') for c in analysis['categories'])):
            raise ValueError(f'Invalid failure_analysis: {entry}')
        cases.append({
            'case_id': case_id, 'repository': match[1], 'issue_number': number,
            'issue_url': url, 'base_commit': case['base_commit'], 'fix_commit': case['fix_commit'],
            'mode': score['mode'],
            'ranked_candidates': [{'rank': i, 'path': p} for i, p in enumerate(score['ranked_files'], 1)],
            'expected_files': score['case']['expected_files'],
            'metrics': score['metrics'], 'matched_files': score['matched_files'],
            'missed_files': score['missed_files'], 'failure_analysis': analysis,
            'case_path': case_path.relative_to(root).as_posix(),
            'result_path': result_path.relative_to(root).as_posix(),
            'inputs_sha256': {'case': case_hash, 'result': result_hash},
        })
    cases.sort(key=lambda c: c['case_id'])
    total = len(cases)
    top1 = sum(c['metrics']['top_1_hit'] for c in cases)
    top3 = sum(c['metrics']['top_3_hit'] for c in cases)
    return {
        'schema_version': 1, 'scorer': 'unique-file-any-hit-v1',
        'manifest_sha256': manifest_hash,
        'summary': {'case_count': total, 'top_1_hits': top1, 'top_3_hits': top3,
                    'top_1_hit_rate': top1 / total, 'top_3_hit_rate': top3 / total},
        'cases': cases,
        'limitations': [
            'Scores saved outputs only; does not rerun an agent or contact a model.',
            'A file hit does not confirm the code region or root cause.',
            'Labels and failure analysis are manually curated; scores do not validate them.',
        ],
    }


def render_markdown(report):
    summary = report['summary']
    def cell(value):
        return str(value).replace('|', '\\|').replace('\n', ' ').replace('\r', '')
    lines = ['# CodeLens 固定输出基线', '',
             f"案例数：{summary['case_count']}。仅评分已保存输出，无网络或模型调用。", '',
             f"Top-1：{summary['top_1_hits']}/{summary['case_count']}（{summary['top_1_hit_rate']:.2%}）；"
             f"Top-3：{summary['top_3_hits']}/{summary['case_count']}（{summary['top_3_hit_rate']:.2%}）。", '',
             '| 案例 | Issue | 修复前提交 | Top-1 | Top-3 | 首次命中排名 |',
             '| --- | --- | --- | --- | --- | --- |']
    for case in report['cases']:
        m = case['metrics']
        lines.append(f"| {cell(case['case_id'])} | [{cell(case['repository'])} #{case['issue_number']}]({case['issue_url']}) | "
                     f"`{case['base_commit']}` | {m['top_1_hit']} | {m['top_3_hit']} | {m['first_relevant_rank']} |")
    for case in report['cases']:
        lines.extend(['', f"## {cell(case['case_id'])}", '',
                      '候选顺序：' + (' → '.join(f"{x['rank']}. `{x['path']}`" for x in case['ranked_candidates']) or '无候选'),
                      '', '真实修复文件：' + ', '.join(f'`{p}`' for p in case['expected_files']), '',
                      f"分析状态：{case['failure_analysis']['status']}；分类：{', '.join(case['failure_analysis']['categories']) or '待分析'}。", '',
                      case['failure_analysis']['reason']])
    lines.extend(['', '## 解释边界', '',
                  '文件命中不代表代码区域或根因已定位。失败分析由人工填写，评分脚本不自动推断根因。',
                  '这是少量同项目案例的描述统计，不是跨项目准确率。版本、输入指纹及完整排名见同名 JSON。', ''])
    return '\n'.join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--manifest', type=Path, required=True)
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--report', type=Path, help='Markdown report; defaults to output with .md suffix')
    args = parser.parse_args(argv)
    try:
        report = evaluate_suite(args.manifest)
        root = args.manifest.resolve().parent
        protected = {args.manifest.resolve()}
        for case in report['cases']:
            protected.update((root / case[k]).resolve() for k in ('case_path', 'result_path'))
        markdown = args.report or args.output.with_suffix('.md')
        outputs = [args.output.resolve(), markdown.resolve()]
        if outputs[0] == outputs[1] or any(p in protected for p in outputs):
            raise ValueError('Outputs must be distinct and must not overwrite inputs')
        encoded = [(json.dumps(report, ensure_ascii=False, indent=2)+'\n').encode('utf-8'),
                   render_markdown(report).encode('utf-8')]
        for path, data in zip(outputs, encoded):
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
    except (ValueError, OSError, UnicodeError) as exc:
        parser.exit(1, f'Benchmark failed: {exc}\n')
    print(json.dumps(report['summary']))


if __name__ == '__main__':
    main()

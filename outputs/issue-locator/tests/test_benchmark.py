"""Aggregate metrics, frozen inputs and reproducible CLI artifacts."""

import hashlib
import json
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest

from issue_locator.benchmark import evaluate_suite


class BenchmarkTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        self.manifest = self.root / 'suite.json'
        self.entries = []

    def write(self, path, value):
        path.write_bytes((json.dumps(value, sort_keys=True)+'\n').encode())

    def add_case(self, paths, number):
        result = self.root / f'result{number}.json'
        self.write(result, {'mode':'offline', 'candidates':[{'path':p} for p in paths]})
        case = self.root / f'case{number}.json'
        self.write(case, {
            'case_id':f'case{number}', 'issue_number':number,
            'issue_url':f'https://github.com/example/project/issues/{number}',
            'base_commit':'a'*40, 'fix_commit':'b'*40,
            'expected_files':['src/fix.py'], 'result_path':result.name,
            'result_sha256':hashlib.sha256(result.read_bytes()).hexdigest()})
        self.entries.append(case.name)
        self.write(self.manifest, {'schema_version':1, 'cases':self.entries})
        return case, result

    def test_three_case_aggregate_and_unique_file_ranks(self):
        self.add_case(['src/fix.py'], 1)
        self.add_case(['a.py','a.py','b.py','src/fix.py'], 2)
        self.add_case(['other.py'], 3)
        report = evaluate_suite(self.manifest)
        self.assertEqual(report['summary'], {'case_count':3,'top_1_hits':1,'top_3_hits':2,
                                            'top_1_hit_rate':1/3,'top_3_hit_rate':2/3})
        self.assertEqual(report['cases'][1]['ranked_candidates'][-1], {'rank':3,'path':'src/fix.py'})
        self.assertEqual(report['cases'][2]['missed_files'], ['src/fix.py'])

    def test_single_case_empty_candidates_and_pending_analysis(self):
        self.add_case([], 1)
        report = evaluate_suite(self.manifest)
        self.assertEqual(report['summary']['case_count'], 1)
        self.assertEqual(report['summary']['top_3_hit_rate'], 0)
        self.assertEqual(report['cases'][0]['failure_analysis']['status'], 'pending')

    def test_changed_output_is_rejected(self):
        _, result = self.add_case([], 1)
        self.write(result, {'candidates':[{'path':'src/fix.py'}]})
        with self.assertRaisesRegex(ValueError, 'SHA-256 mismatch'):
            evaluate_suite(self.manifest)

    def test_missing_invalid_empty_or_duplicate_cases_are_not_skipped(self):
        case, result = self.add_case([], 1)
        original = case.read_bytes()
        for entries in ([], [case.name,case.name], [case.name,'missing.json']):
            with self.subTest(entries=entries):
                self.write(self.manifest, {'schema_version':1,'cases':entries})
                with self.assertRaises((ValueError,OSError)):
                    evaluate_suite(self.manifest)
        self.write(self.manifest, {'schema_version':1,'cases':[case.name]})
        for change in ({'base_commit':'main'}, {'issue_number':2}, {'expected_files':[]},
                       {'failure_analysis':{'status':'analyzed','categories':[],'reason':''}},
                       {'result_path':'../outside.json'}):
            with self.subTest(change=change):
                value = json.loads(original)
                value.update(change)
                self.write(case,value)
                with self.assertRaises(ValueError):
                    evaluate_suite(self.manifest)
        case.write_bytes(original)
        result.unlink()
        with self.assertRaises(OSError):
            evaluate_suite(self.manifest)

    def test_same_issue_with_another_id_is_rejected(self):
        case1,_ = self.add_case([],1)
        case2,_ = self.add_case([],2)
        value=json.loads(case2.read_bytes())
        value.update(issue_number=1,issue_url=json.loads(case1.read_bytes())['issue_url'])
        self.write(case2,value)
        with self.assertRaisesRegex(ValueError,'Duplicate'):
            evaluate_suite(self.manifest)

    def test_cli_repeatability_without_site_packages_and_input_protection(self):
        case,result = self.add_case(['src/fix.py'],1)
        command=[sys.executable,'-S','-m','issue_locator.benchmark','--manifest',str(self.manifest),'--output']
        first=self.root/'reports/first.json'
        second=self.root/'reports/second.json'
        for output in (first,second):
            run=subprocess.run(command+[str(output)],capture_output=True,text=True)
            self.assertEqual(run.returncode,0,run.stderr)
        self.assertEqual(first.read_bytes(),second.read_bytes())
        self.assertEqual(first.with_suffix('.md').read_bytes(),second.with_suffix('.md').read_bytes())
        for protected in (self.manifest,case,result):
            original=protected.read_bytes()
            run=subprocess.run(command+[str(protected)],capture_output=True,text=True)
            self.assertNotEqual(run.returncode,0)
            self.assertEqual(protected.read_bytes(),original)
            self.assertNotIn('Traceback',run.stderr)
        result.write_bytes(b'broken json')
        original=first.read_bytes()
        run=subprocess.run(command+[str(first)],capture_output=True,text=True)
        self.assertNotEqual(run.returncode,0)
        self.assertEqual(first.read_bytes(),original)


if __name__ == '__main__':
    unittest.main()

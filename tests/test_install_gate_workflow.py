"""Keep ordinary manual validation separate from billable model sessions."""
import re
import unittest
from pathlib import Path


class InstallGateWorkflowTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.workflow = (Path(__file__).resolve().parents[1] /
                        '.github/workflows/install-gate.yml').read_text(encoding='utf-8')

    def test_manual_inputs_default_to_no_external_actions(self):
        dispatch = self.workflow.split('  workflow_dispatch:\n', 1)[1].split('\npermissions:', 1)[0]
        for name in ('run_live', 'public_install'):
            with self.subTest(input=name):
                match = re.search(r'^      ' + name + r':\n((?:        [^\n]*\n)+)',
                                  dispatch, re.MULTILINE)
                self.assertIsNotNone(match, f'missing explicit {name} dispatch input')
                body = match.group(1)
                self.assertIn('        type: boolean\n', body)
                self.assertIn('        default: false\n', body)

    def test_live_job_requires_separate_explicit_opt_in(self):
        live = self.workflow.split('\n  live:\n', 1)[1]
        conditions = re.findall(r'^    if: (.+)$', live, re.MULTILINE)
        self.assertEqual(conditions, ["github.event_name == 'workflow_dispatch' && inputs.run_live"],
                         'ordinary manual diagnostics must not launch billable Claude sessions')


if __name__ == '__main__':
    unittest.main()

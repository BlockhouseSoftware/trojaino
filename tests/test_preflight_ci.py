"""Static CI contract checks, not evidence of a Windows test run."""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/preflight-windows.yml'

class NativeWindowsCIContract(unittest.TestCase):
    def test_native_job_is_bounded_read_only_and_records_tests(self):
        self.assertTrue(WORKFLOW.is_file(), 'Native Windows preflight job is missing')
        text = WORKFLOW.read_text()
        for required in ('runs-on: windows-2025', 'timeout-minutes: 15',
                         'contents: read', 'persist-credentials: false',
                         'python -m unittest discover -s tests -v',
                         '$LASTEXITCODE', 'if: always()', 'preflight-evidence'):
            self.assertIn(required, text)
        self.assertNotIn('pull_request_target:', text)
        self.assertNotIn('secrets.', text)
        self.assertNotIn('permissions: write-all', text)

if __name__ == '__main__':
    unittest.main()

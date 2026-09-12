"""Static CI contract checks, not evidence of a Windows test run."""
from pathlib import Path
import unittest

WORKFLOW = Path(__file__).resolve().parents[1] / '.github/workflows/preflight-windows.yml'

class NativeWindowsCIContract(unittest.TestCase):
    def test_pull_request_paths_cover_shipped_helpers_and_setup_docs(self):
        text = WORKFLOW.read_text()
        pull_request = text.split('  pull_request:\n', 1)[1].split('\n\n', 1)[0]
        paths = {
            line.strip()[2:].strip('"\'')
            for line in pull_request.split('    paths:\n', 1)[1].splitlines()
            if line.strip().startswith('- ')
        }
        required = {
            'scripts/build_preflight_bundle.py',
            'scripts/prepare_preflight_plugin.py',
            'scripts/build_sealed_runtime.py',
            'scripts/sealed_runtime_bootstrap.py',
            'scripts/write_prepared_tree.py',
            'docs/windows-preflight.md',
            'docs/sig-windows-trial.md',
            'docs/personal-plugin-delivery.md',
            'docs/marketplace-lifecycle.md',
            'docs/marketplace-requirements.md',
            'docs/marketplace-runtime-architecture.md',
            '.claude-plugin/**',
            'README.md',
            'plugins/trojaino/**',
        }
        self.assertFalse(required - paths, f'Missing PR paths: {sorted(required - paths)}')

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

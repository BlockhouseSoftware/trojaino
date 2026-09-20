"""plugins/trojaino is generated from the packaged payload, not edited in place."""
import json
from pathlib import Path
import unittest

from trojaino.claude import payload

ROOT = Path(__file__).resolve().parents[1]
PLUGIN = ROOT / 'plugins/trojaino'


class PayloadIsCanonicalTests(unittest.TestCase):
    def test_checked_in_plugin_matches_a_fresh_generation(self):
        generated = payload.marketplace_files()
        on_disk = {
            str(path.relative_to(PLUGIN)).replace('\\', '/'): path.read_bytes()
            for path in sorted(PLUGIN.rglob('*')) if path.is_file()
        }
        self.assertEqual(sorted(on_disk), sorted(generated),
                         'plugins/trojaino file set drifted from the payload')
        for name, data in generated.items():
            self.assertEqual(on_disk[name], data,
                             f'{name} was edited in plugins/trojaino instead of the payload; '
                             'run scripts/generate_plugin_dir.py')

    def test_distributed_copy_registers_no_hooks(self):
        hooks = json.loads(payload.marketplace_files()['hooks/hooks.json'])
        self.assertEqual(hooks, {'hooks': {}})

    def test_payload_license_matches_the_project_license(self):
        self.assertEqual((payload.PAYLOAD / 'LICENSE').read_bytes(),
                         (ROOT / 'LICENSE').read_bytes())

    def test_payload_carries_no_hooks_or_entry_of_its_own(self):
        # Those are produced at generation time; a stale copy here could ship.
        names = {path.name for path in payload.PAYLOAD.iterdir()}
        self.assertNotIn('hooks.json', names)
        self.assertNotIn('preflight.py', names)


if __name__ == '__main__':
    unittest.main()

"""Preparation must write via pinned directories, not mutable path strings."""
import os
from pathlib import Path
import runpy
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]

@unittest.skipUnless(os.name == 'posix', 'POSIX descriptor replacement test')
class PreparedTreeTests(unittest.TestCase):
    def test_existing_real_directory_substitution_is_not_merged(self):
        writer = runpy.run_path(str(ROOT / 'scripts/write_prepared_tree.py'))['write_tree']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            destination = root / 'prepared'
            existing = root / 'existing'
            existing.mkdir(mode=0o700)
            (existing / 'unexpected.txt').write_text('existing data')
            original = os.open
            swapped = False
            def opened(path, flags, *args, **kwargs):
                nonlocal swapped
                if str(path) == 'prepared' and flags & os.O_DIRECTORY and not swapped:
                    swapped = True
                    destination.rename(root / 'old')
                    existing.rename(destination)
                return original(path, flags, *args, **kwargs)
            with patch('os.open', side_effect=opened):
                with self.assertRaises((OSError, ValueError)):
                    writer(destination, {'scripts/entry.py': b'print(42)\n'})
            self.assertTrue(swapped)
            self.assertFalse((destination / 'scripts').exists())

    def test_ancestor_rename_is_not_reported_as_publication_success(self):
        writer = runpy.run_path(str(ROOT / 'scripts/write_prepared_tree.py'))['write_tree']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            ancestor = root / 'ancestor'
            ancestor.mkdir()
            outside = root / 'outside'
            outside.mkdir()
            original = os.open
            swapped = False
            def opened(path, flags, *args, **kwargs):
                nonlocal swapped
                fd = original(path, flags, *args, **kwargs)
                if str(path) == 'prepared' and flags & os.O_DIRECTORY and not swapped:
                    swapped = True
                    ancestor.rename(root / 'moved')
                    ancestor.symlink_to(outside, target_is_directory=True)
                return fd
            with patch('os.open', side_effect=opened):
                with self.assertRaises((OSError, ValueError)):
                    writer(ancestor / 'prepared', {'entry.py': b'print(42)\n'})
            self.assertTrue(swapped)
            self.assertEqual(list(outside.iterdir()), [])

    def test_destination_swap_cannot_redirect_writes(self):
        helper = ROOT / 'scripts/write_prepared_tree.py'
        self.assertTrue(helper.is_file(), 'pinned tree writer required')
        writer = runpy.run_path(str(helper))['write_tree']
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp).resolve()
            destination = root / 'prepared'
            outside = root / 'outside'
            outside.mkdir()
            real_open = os.open
            swapped = False
            def opened(path, flags, *args, **kwargs):
                nonlocal swapped
                fd = real_open(path, flags, *args, **kwargs)
                if str(path) == 'prepared' and flags & os.O_DIRECTORY and not swapped:
                    swapped = True
                    destination.rename(root / 'moved')
                    destination.symlink_to(outside, target_is_directory=True)
                return fd
            with patch('os.open', side_effect=opened):
                with self.assertRaises((OSError, ValueError)):
                    writer(destination, {'scripts/entry.py': b'print(42)\n'})
            self.assertTrue(swapped)
            self.assertEqual(list(outside.iterdir()), [])

if __name__ == '__main__':
    unittest.main()

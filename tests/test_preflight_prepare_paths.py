"""WP-004: reject raw Windows destinations before normalization or I/O.

Portable boundary tests, not native Windows filesystem qualification.
"""
import argparse
from contextlib import ExitStack
from pathlib import Path
import runpy
import sys
from types import SimpleNamespace
import unittest
from unittest import mock

from scripts import prepare_preflight_plugin as prepare_cli
from trojaino.claude import prepare as prepare_script
from trojaino.preflight_paths import windows_path


INVALID_DESTINATIONS = (
    'C:\\trusted\\.\\new',
    'C:\\trusted\\..\\new',
    'C:\\trusted\\\\new',
    'C:\\trusted\\new\\',
    'C:/trusted/./new',
    'C:/trusted//new',
    'C:/trusted/new/',
    '\\\\server\\share\\new',
    '\\\\?\\C:\\trusted\\new',
    '\\\\.\\C:\\trusted\\new',
    'C:\\bad\ud800',
    'C:\\bad\udfff',
    'C:\\' + '\U0001f600' * 118 + 'a',  # 240 UTF-16 units
    'C:\\' + '\U0001f600' * 119,  # 241 units despite fewer code points
    'C:\\' + 'x' * 256,
)


class PreparationRawPathTests(unittest.TestCase):
    def test_invalid_raw_destinations_rejected_before_path_or_io(self):
        for raw in INVALID_DESTINATIONS:
            with self.subTest(raw=repr(raw)), ExitStack() as stack:
                stack.enter_context(mock.patch.object(prepare_script, 'os', SimpleNamespace(name='nt')))
                stack.enter_context(mock.patch.object(sys, 'path', list(sys.path)))
                validate = stack.enter_context(mock.patch(
                    'trojaino.preflight_paths.windows_path', wraps=windows_path))
                executable = Path(sys.executable)

                def guarded_path(value):
                    if value == sys.executable:
                        return executable
                    raise AssertionError('destination Path before validation')

                construct = stack.enter_context(mock.patch.object(
                    prepare_script, 'Path', side_effect=guarded_path))
                probes = [stack.enter_context(mock.patch.object(
                    Path, method, side_effect=AssertionError('filesystem before validation')))
                    for method in ('exists', 'is_symlink', 'stat', 'lstat', 'mkdir', 'open')]
                with self.assertRaisesRegex(ValueError, 'unsafe_windows_path|unsupported_windows_path_length'):
                    prepare_script.prepare(raw)
                validate.assert_called_once_with(raw)
                construct.assert_called_once_with(sys.executable)
                for probe in probes:
                    probe.assert_not_called()

    def test_cli_keeps_destination_raw_until_prepare(self):
        original_parse = argparse.ArgumentParser.parse_args

        class ParsedWithoutIO(Exception):
            pass

        for raw in INVALID_DESTINATIONS:
            def inspect_parse(parser, *args, **kwargs):
                parsed = original_parse(parser, *args, **kwargs)
                self.assertIsInstance(parsed.destination, str)
                self.assertEqual(parsed.destination, raw)
                raise ParsedWithoutIO

            with self.subTest(raw=repr(raw)), mock.patch.object(
                    sys, 'argv', [str(prepare_cli.ROOT / 'scripts/prepare_preflight_plugin.py'), raw]), mock.patch.object(
                    argparse.ArgumentParser, 'parse_args', inspect_parse):
                with self.assertRaises(ParsedWithoutIO):
                    runpy.run_path(str(prepare_cli.ROOT / 'scripts/prepare_preflight_plugin.py'), run_name='__main__')

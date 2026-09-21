"""Staleness signalling: local-only, fails silent, and never phones home."""
from datetime import date
import json
from pathlib import Path
import re
import tempfile
import unittest
from unittest import mock

from trojaino import freshness


def _catalog(tmp: Path, ref: str, name: str = 'trojaino') -> Path:
    config, catalog = tmp / 'config', tmp / 'catalog'
    (catalog / '.claude-plugin').mkdir(parents=True)
    (catalog / '.claude-plugin/marketplace.json').write_text(json.dumps(
        {'name': 'blockhouse-software',
         'plugins': [{'name': name, 'source': {'source': 'git-subdir', 'ref': ref}}]}))
    (config / 'plugins').mkdir(parents=True)
    (config / 'plugins/known_marketplaces.json').write_text(json.dumps(
        {'blockhouse-software': {'installLocation': str(catalog)}}))
    return config


class ReleaseDateTests(unittest.TestCase):
    def test_release_date_matches_the_changelog(self):
        from trojaino import __version__
        from trojaino._release import RELEASE_DATE
        changelog = (Path(__file__).resolve().parents[1] / 'CHANGELOG.md').read_text(encoding='utf-8')
        heading = re.search(rf'^## {re.escape(__version__)} - (\d{{4}}-\d{{2}}-\d{{2}})',
                            changelog, re.M)
        self.assertIsNotNone(heading, f'CHANGELOG has no dated entry for {__version__}')
        self.assertEqual(RELEASE_DATE, heading.group(1),
                         'trojaino/_release.py drifted from the CHANGELOG')


class AgeTests(unittest.TestCase):
    def test_age_counts_forward_and_never_goes_negative(self):
        with mock.patch.object(freshness, 'RELEASE_DATE', '2026-09-18'):
            self.assertEqual(freshness.age_in_days(date(2026, 9, 18)), 0)
            self.assertEqual(freshness.age_in_days(date(2026, 12, 21)), 94)
            self.assertEqual(freshness.age_in_days(date(2026, 1, 1)), 0)

    def test_unparseable_release_date_is_not_fatal(self):
        with mock.patch.object(freshness, 'RELEASE_DATE', 'not-a-date'):
            self.assertIsNone(freshness.age_in_days())
            self.assertIsNone(freshness.reminder('0.2.0'))


class CatalogTests(unittest.TestCase):
    def test_reads_the_version_a_local_catalog_advertises(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = _catalog(Path(tmp), 'v0.3.0')
            self.assertEqual(freshness.advertised_version(config), '0.3.0')

    def test_branch_refs_and_other_plugins_are_ignored(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(freshness.advertised_version(_catalog(Path(tmp), 'main')))
        with tempfile.TemporaryDirectory() as tmp:
            self.assertIsNone(freshness.advertised_version(_catalog(Path(tmp), 'v9.9.9', name='other')))

    def test_every_malformed_input_degrades_silently(self):
        with tempfile.TemporaryDirectory() as tmp:
            config = Path(tmp) / 'config'
            (config / 'plugins').mkdir(parents=True)
            known = config / 'plugins/known_marketplaces.json'
            for content in ('{ not json', json.dumps([]), json.dumps({'a': 5}),
                            json.dumps({'a': {'installLocation': 42}}),
                            json.dumps({'a': {'installLocation': '/nonexistent'}})):
                with self.subTest(content=content[:30]):
                    known.write_text(content)
                    self.assertIsNone(freshness.advertised_version(config))
        self.assertIsNone(freshness.advertised_version(Path('/definitely/not/here')))


class ReminderTests(unittest.TestCase):
    def test_silent_before_the_threshold(self):
        with mock.patch.object(freshness, 'RELEASE_DATE', '2026-09-18'):
            self.assertIsNone(freshness.reminder('0.2.0', today=date(2026, 10, 1),
                                                 config_dir=Path('/nonexistent')))

    def test_names_the_newer_version_when_a_catalog_knows_one(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(freshness, 'RELEASE_DATE', '2026-09-18'):
            config = _catalog(Path(tmp), 'v0.3.0')
            text = freshness.reminder('0.2.0', today=date(2026, 12, 21), config_dir=config)
            self.assertIn('0.3.0', text)
            self.assertIn('94 days', text)

    def test_falls_back_to_age_when_no_catalog_is_readable(self):
        with mock.patch.object(freshness, 'RELEASE_DATE', '2026-09-18'):
            text = freshness.reminder('0.2.0', today=date(2026, 12, 21),
                                      config_dir=Path('/nonexistent'))
            self.assertIn('check-updates', text)
            self.assertNotIn('available', text.split('.')[0])

    def test_same_version_in_the_catalog_is_not_reported_as_an_update(self):
        with tempfile.TemporaryDirectory() as tmp, \
                mock.patch.object(freshness, 'RELEASE_DATE', '2026-09-18'):
            config = _catalog(Path(tmp), 'v0.2.0')
            text = freshness.reminder('0.2.0', today=date(2026, 12, 21), config_dir=config)
            self.assertIn('check-updates', text)


class GatingTests(unittest.TestCase):
    def test_fires_at_most_once_per_window(self):
        with tempfile.TemporaryDirectory() as tmp:
            stamp = Path(tmp) / 'stamp'
            self.assertTrue(freshness.due(date(2026, 12, 21), stamp))
            self.assertFalse(freshness.due(date(2026, 12, 21), stamp))
            self.assertFalse(freshness.due(date(2027, 1, 1), stamp))
            self.assertTrue(freshness.due(date(2027, 3, 1), stamp))

    def test_unwritable_location_stays_quiet_rather_than_raising(self):
        # A stamp whose parent is a regular file: mkdir cannot succeed on any
        # platform. An unwritable system path would not do, because a path like
        # /proc does not exist on Windows and the runner would simply create it.
        with tempfile.TemporaryDirectory() as tmp:
            blocker = Path(tmp) / 'not-a-directory'
            blocker.write_text('', encoding='utf-8')
            self.assertFalse(freshness.due(date(2026, 12, 21), blocker / 'stamp'))

    def test_session_reminder_never_raises(self):
        with mock.patch.object(freshness, 'due', side_effect=RuntimeError('boom')):
            self.assertEqual(freshness.session_reminder('0.2.0'), '')


if __name__ == '__main__':
    unittest.main()

"""check-updates is the only networked command, and it fails soft."""
import json
import unittest
from unittest import mock
from urllib.error import URLError

from trojaino.claude import updates


class CheckUpdatesTests(unittest.TestCase):
    def test_reports_a_newer_release(self):
        with mock.patch.object(updates, 'latest_released_version', return_value='0.3.0'):
            outcome = updates.check('0.2.0')
        self.assertTrue(outcome['reachable'])
        self.assertTrue(outcome['newer_available'])
        self.assertEqual(outcome['latest'], '0.3.0')

    def test_reports_being_current(self):
        with mock.patch.object(updates, 'latest_released_version', return_value='0.2.0'):
            self.assertFalse(updates.check('0.2.0')['newer_available'])

    def test_offline_is_reported_not_raised(self):
        for failure in (URLError('no route'), TimeoutError('slow'), OSError('down'),
                        ValueError('package index returned no version')):
            with self.subTest(failure=type(failure).__name__), \
                    mock.patch.object(updates, 'latest_released_version', side_effect=failure):
                outcome = updates.check('0.2.0')
                self.assertFalse(outcome['reachable'])
                self.assertIsNone(outcome['latest'])
                self.assertTrue(outcome['error'])

    def test_index_target_is_a_fixed_https_url(self):
        self.assertTrue(updates.INDEX_URL.startswith('https://pypi.org/'))

    def test_nothing_is_fetched_unless_check_is_called(self):
        with mock.patch.object(updates, 'urlopen') as opener:
            from trojaino import freshness
            freshness.reminder('0.2.0')
            freshness.advertised_version()
            freshness.age_in_days()
            opener.assert_not_called()

    def test_malformed_index_response_is_rejected(self):
        class Fake:
            def __enter__(self): return self
            def __exit__(self, *a): return False
            def read(self, *a): return json.dumps({'info': {}}).encode()
        with mock.patch.object(updates, 'urlopen', return_value=Fake()):
            with self.assertRaises(ValueError):
                updates.latest_released_version()


if __name__ == '__main__':
    unittest.main()

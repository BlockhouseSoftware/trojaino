"""Portable regression of the native ACL assertion, not Win32 simulation."""
import copy
import unittest
from preflight_test_support import assert_private_dacl


class PrivateDaclAssertionTests(unittest.TestCase):
    sid = 'S-1-5-21-111-222-333-500'

    def snapshot(self):
        return {
            'sddl': 'O:BAG:S-1-5-21-111-222-333-513D:P(A;OICI;FA;;;SY)(A;OICI;FA;;;LA)',
            'protected': True,
            'rules': [dict(sid=sid, type=0, rights=2032127, inherited=False,
                           inheritance=3, propagation=0)
                      for sid in ['S-1-5-18', self.sid]],
        }

    def test_numeric_token_user_is_accepted_despite_la_sddl_alias(self):
        assert_private_dacl(self, self.snapshot(), self.sid)

    def test_alias_does_not_authorize_a_different_token_user(self):
        with self.assertRaises(AssertionError):
            assert_private_dacl(self, self.snapshot(), 'S-1-5-21-111-222-333-1001')

    def test_rejects_unprotected_inherited_broad_missing_and_nonfull_rules(self):
        good = self.snapshot()
        variants = []
        changed = copy.deepcopy(good)
        changed['protected'] = False
        variants.append(changed)
        for field, value in [('sid', 'S-1-1-0'), ('type', 1), ('rights', 1179785),
                             ('inherited', True), ('inheritance', 0), ('propagation', 1)]:
            changed = copy.deepcopy(good)
            changed['rules'][1][field] = value
            variants.append(changed)
        for rules in [good['rules'][:1], good['rules'] * 2,
                      good['rules'] + [dict(good['rules'][0], sid='S-1-5-32-544')]]:
            variants.append(dict(good, rules=rules))
        for snapshot in variants:
            with self.subTest(snapshot=snapshot), self.assertRaises(AssertionError):
                assert_private_dacl(self, snapshot, self.sid)

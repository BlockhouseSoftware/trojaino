"""Trusted fixture setup, never canonicalize an untrusted gate input."""
from pathlib import Path
import tempfile


def assert_private_dacl(case, snapshot, token_user_sid):
    """Check numeric SecurityIdentifier rules, never localized SDDL aliases."""
    case.assertIs(snapshot['protected'], True, snapshot)
    rules = snapshot['rules']
    case.assertEqual(len(rules), 2, snapshot)
    case.assertCountEqual([rule['sid'] for rule in rules],
                          ['S-1-5-18', token_user_sid], snapshot)
    for rule in rules:
        case.assertIs(rule['inherited'], False, snapshot)
        case.assertEqual(rule['type'], 0, snapshot)  # AccessControlType.Allow
        case.assertEqual(rule['rights'], 2032127, snapshot)  # FullControl
        case.assertEqual(rule['inheritance'], 3, snapshot)  # Object + Container
        case.assertEqual(rule['propagation'], 0, snapshot)  # None


class TemporaryDirectory(tempfile.TemporaryDirectory):
    """Expand the trusted runner's TEMP alias before constructing test inputs.

    Keep tempfile's original cleanup target/finalizer; only expose the canonical
    spelling. Production locked_path must continue rejecting aliases.
    """
    def __enter__(self):
        return str(Path(super().__enter__()).resolve(strict=True))

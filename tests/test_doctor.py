"""Readiness must detect disabled and conflicting installations without mutation."""
import json
import os
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from trojaino import __version__
from trojaino.doctor import inspect_registration

class RegistrationTests(unittest.TestCase):
    def test_enabled_disabled_and_legacy_settings(self):
        with tempfile.TemporaryDirectory() as tmp:
            base=Path(tmp)
            config=base/'claude'
            root=base/'plugin'
            root.mkdir()
            (config/'plugins').mkdir(parents=True)
            (config/'plugins/installed_plugins.json').write_text(json.dumps({'plugins':{'trojaino@blockhouse-software':[
                {'installPath':str(root),'version':__version__}]}}))
            settings=config/'settings.json'
            settings.write_text(json.dumps({'enabledPlugins':{'trojaino@blockhouse-software':True}}))
            with patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':str(config)}):
                self.assertEqual(inspect_registration(root,base),[])
                local=base/'.claude'
                local.mkdir()
                local_settings=local/'settings.local.json'
                local_settings.write_text('{"enabledPlugins":{"trojaino@blockhouse-software":false}}')
                self.assertTrue(any('not enabled' in p for p in inspect_registration(root,base)))
                local_settings.write_text('{"disableAllHooks":true,"hooks":{"PreToolUse":"trojaino prepared launcher"}}')
                original=local_settings.read_bytes()
                problems=inspect_registration(root,base)
                self.assertTrue(any('disabled' in p for p in problems))
                self.assertTrue(any('Legacy' in p for p in problems))
                self.assertEqual(local_settings.read_bytes(),original)

    def test_missing_registration_never_reports_ready(self):
        with tempfile.TemporaryDirectory() as tmp, patch.dict(os.environ,{'CLAUDE_CONFIG_DIR':tmp}):
            problems=inspect_registration(Path(tmp)/'plugin',Path(tmp))
            self.assertTrue(any('registration' in p for p in problems))

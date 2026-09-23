"""Ordinary developer setups must not turn clean installs into approval prompts.

Each case is a configuration seen on real machines: an npm login token, a proxy
that sets PIP_CONFIG_FILE, a dotfile manager's symlink, "cd project && npm i".
Settings that really change the source still need review.
"""
import json
import os
from pathlib import Path
from unittest.mock import patch

from tests.test_gate import GateTestCase
from tests.gate_fixtures import tgz, wheel
from trojaino import registry


class OrdinaryConfigurationTests(GateTestCase):
    def setUp(self):
        super().setUp()
        self.fake.npm('good', {'1.0.0': tgz({'index.js': '1'})})
        self.fake.npm('@corp/tool', {'1.0.0': tgz({'index.js': '1'})})
        self.fake.pypi('pkg', '1.0', [('pkg-1.0-py3-none-any.whl', wheel({'pkg.py': '1'}), 'bdist_wheel')])
        self.home_dir = Path(self.home.name)
        self.project = self.home_dir / 'project'
        self.project.mkdir()

    def assert_clean(self, command, cwd=None, pinned=None):
        out = self.output(self.decide(command, cwd=str(cwd or self.project)))
        self.assertNotIn('permissionDecision', out, out.get('permissionDecisionReason'))
        if pinned:
            self.assertEqual(out['updatedInput']['command'], pinned)
        return out

    def assert_review(self, command, cwd=None, tool='Bash'):
        out = self.output(self.decide(command, tool=tool, cwd=str(cwd or self.project)))
        self.assertEqual(out['permissionDecision'], 'ask')
        self.assertNotIn('updatedInput', out)
        return out

    # npm ---------------------------------------------------------------

    def test_npm_login_token_is_not_a_registry_override(self):
        (self.home_dir / '.npmrc').write_text('//registry.npmjs.org/:_authToken=npm_SECRET\n'
                                              'always-auth=true\nfund=false\n')
        self.assert_clean('npm install good', pinned='npm install good@1.0.0')

    def test_default_registry_spelled_out_is_not_an_override(self):
        (self.home_dir / '.npmrc').write_text('registry = "https://registry.npmjs.org/"\n')
        self.assert_clean('npm install good')
        with patch.dict(os.environ, {'npm_config_registry': 'https://registry.npmjs.org/'}):
            self.assert_clean('npm install good')

    def test_private_registry_still_needs_review_without_leaking_it(self):
        (self.home_dir / '.npmrc').write_text('registry=https://token-SECRET@npm.corp.example/\n')
        out = self.assert_review('npm install good')
        self.assertNotIn('SECRET', json.dumps(out))
        self.assertFalse(self.fake.requests)

    def test_scoped_registry_applies_only_to_its_scope(self):
        (self.home_dir / '.npmrc').write_text('@corp:registry=https://npm.corp.example/\n')
        self.assert_clean('npm install good')
        self.assert_review('npm install @corp/tool')

    def test_config_file_pointer_is_read_not_rejected(self):
        proxy_only = self.home_dir / 'proxy.npmrc'
        proxy_only.write_text('https-proxy=http://proxy.example:3128\ncafile=/etc/ssl/corp.pem\n')
        with patch.dict(os.environ, {'NPM_CONFIG_USERCONFIG': str(proxy_only)}):
            self.assert_clean('npm install good')
            proxy_only.write_text('registry=https://npm.corp.example/\n')
            self.assert_review('npm install good')

    def test_symlinked_dotfile_is_followed(self):
        real = self.home_dir / 'dotfiles-npmrc'
        real.write_text('//registry.npmjs.org/:_authToken=npm_SECRET\n')
        (self.home_dir / '.npmrc').symlink_to(real)
        self.assert_clean('npm install good')

    def test_package_overrides_matter_only_for_the_named_package(self):
        (self.project / 'package.json').write_text(json.dumps(
            {'name': 'app', 'overrides': {'lodash': '4.17.21'}, 'resolutions': {'**/minimist': '1.2.8'}}))
        self.assert_clean('npm install good')
        (self.project / 'package.json').write_text(json.dumps({'name': 'app', 'overrides': {'good': '0.9.0'}}))
        self.assert_review('npm install good')

    def test_unrelated_short_options_elsewhere_in_the_command_are_ignored(self):
        self.assert_clean('rm -f package-lock.json && npm install good',
                          pinned='rm -f package-lock.json && npm install good@1.0.0')
        self.assert_clean('grep -i name package.json; npm install good')

    def test_powershell_environment_assignment_is_recognized(self):
        self.assert_review("$env:NPM_CONFIG_REGISTRY = 'https://npm.corp.example'; npm install good",
                           tool='PowerShell')

    # working directory --------------------------------------------------

    def test_leading_cd_is_resolved_and_kept(self):
        elsewhere = self.home_dir / 'elsewhere'
        elsewhere.mkdir()
        self.assert_clean(f'cd {self.project} && npm install good', cwd=elsewhere,
                          pinned=f'cd {self.project} && npm install good@1.0.0')
        self.assert_clean('cd project && npm install good', cwd=self.home_dir)

    def test_cd_target_configuration_is_the_one_inspected(self):
        (self.project / '.npmrc').write_text('registry=https://npm.corp.example/\n')
        elsewhere = self.home_dir / 'elsewhere'
        elsewhere.mkdir()
        self.assert_clean('npm install good', cwd=elsewhere)
        self.assert_review(f'cd {self.project} && npm install good', cwd=elsewhere)

    def test_unknowable_directory_changes_still_need_review(self):
        for command in ('cd missing && npm install good', 'cd a && cd b && npm install good',
                        'mkdir x && cd x && npm install good', 'cd $DIR && npm install good'):
            with self.subTest(command=command):
                self.assert_review(command)

    def test_relative_local_install_follows_the_cd(self):
        (self.project / 'tool').mkdir()
        (self.project / 'tool' / 'index.js').write_text('module.exports = 1\n')
        out = self.output(self.decide('cd project && npm install ./tool', cwd=str(self.home_dir)))
        self.assertIn('tool: NO CRITICAL RISKS FOUND (1 files scanned)', out['permissionDecisionReason'])

    # Python --------------------------------------------------------------

    def test_pip_config_pointer_with_only_proxy_settings_is_clean(self):
        conf = self.home_dir / 'pip.conf'
        conf.write_text('[global]\nproxy = http://proxy.example:3128\ncert = /etc/ssl/corp.pem\ntimeout = 60\n')
        with patch.dict(os.environ, {'PIP_CONFIG_FILE': str(conf), 'PIP_CERT': '/etc/ssl/corp.pem'}):
            self.assert_clean('pip install pkg')
            conf.write_text('[global]\nindex-url = https://pypi.corp.example/simple\n')
            self.assert_review('pip install pkg')

    def test_pip_default_index_is_not_an_override(self):
        with patch.dict(os.environ, {'PIP_INDEX_URL': 'https://pypi.org/simple/'}):
            self.assert_clean('pip install pkg')
        with patch.dict(os.environ, {'PIP_INDEX_URL': 'https://pypi.corp.example/simple'}):
            self.assert_review('pip install pkg')

    def test_uv_project_settings_matter_only_when_they_select_sources(self):
        (self.project / 'pyproject.toml').write_text(
            '[project]\nname = "app"\n[tool.uv]\ndev-dependencies = ["pytest"]\n')
        self.assert_clean('uv add pkg', pinned='uv add pkg==1.0')
        (self.project / 'pyproject.toml').write_text(
            '[project]\nname = "app"\n[[tool.uv.index]]\nurl = "https://pypi.corp.example/simple"\n')
        self.assert_review('uv add pkg')

    def test_uv_settings_do_not_affect_pip(self):
        (self.project / 'uv.toml').write_text('index-url = "https://pypi.corp.example/simple"\n')
        self.assert_review('uv pip install pkg')
        self.assert_clean('pip install pkg')


class PythonBindingTests(GateTestCase):
    """Bind to the file Trojaino scanned, or ask; never force a surprising build."""

    def test_sdist_with_compiled_wheels_asks_instead_of_forcing_a_source_build(self):
        self.fake.pypi('native', '2.0', [
            ('native-2.0.tar.gz', tgz({'native/__init__.py': 'x = 1\n'}, root='native-2.0'), 'sdist'),
            ('native-2.0-cp312-cp312-manylinux_2_17_x86_64.whl', wheel({'native/_c.so': b'\x7fELF'}),
             'bdist_wheel')])
        for command in ('pip install native', 'uv add native', 'uvx native'):
            with self.subTest(command=command):
                out = self.output(self.decide(command))
                self.assertEqual(out['permissionDecision'], 'ask')
                self.assertIn('compiled wheels', out['permissionDecisionReason'])
                self.assertNotIn('updatedInput', out)

    def test_pure_wheel_among_platform_wheels(self):
        self.fake.pypi('mixed', '3.0', [
            ('mixed-3.0-py3-none-any.whl', wheel({'mixed/__init__.py': 'x = 1\n'}), 'bdist_wheel'),
            ('mixed-3.0-cp312-cp312-win_amd64.whl', wheel({'mixed/_speedups.pyd': b'MZ'}), 'bdist_wheel')])
        artifact = registry.resolve_pypi('mixed', None)
        out = self.output(self.decide('pip install mixed'))
        self.assertEqual(out['updatedInput']['command'],
                         "pip install 'mixed @ " + artifact.url + '#sha256=' + artifact.digest[7:] + "'")
        out = self.output(self.decide('uv add mixed'))
        self.assertEqual(out['permissionDecision'], 'ask')
        self.assertIn('several installable files', out['permissionDecisionReason'])

    def test_source_only_release_binds_both_ways(self):
        self.fake.pypi('plain', '0.5', [('plain-0.5.tar.gz', tgz({'plain.py': 'x = 1\n'}, root='plain-0.5'),
                                         'sdist')])
        artifact = registry.resolve_pypi('plain', None)
        out = self.output(self.decide('pip install plain'))
        self.assertIn(artifact.url + '#sha256=', out['updatedInput']['command'])
        self.assertEqual(self.output(self.decide('uv add plain'))['updatedInput']['command'], 'uv add plain==0.5')


class DevelopmentFolderTests(GateTestCase):
    """psutil 7.2.2 was blocked for os.system in scripts/ and eval in tests/."""

    RISKY = 'import os, sys\nos.system("taskset -c 0 " + sys.argv[1])\nos.system("git clean -fdx " + sys.argv[2])\n'

    def sdist(self, name, files):
        self.fake.pypi(name, '1.0', [(f'{name}-1.0.tar.gz', tgz(files, root=f'{name}-1.0'), 'sdist')])

    def test_findings_only_in_development_folders_ask_instead_of_blocking(self):
        self.sdist('toolkit', {'toolkit/__init__.py': 'VALUE = 1\n', 'scripts/bench.py': self.RISKY,
                               'tests/test_x.py': self.RISKY})
        for attempt in range(2):  # the second answer comes from the verdict cache
            with self.subTest(attempt=attempt):
                out = self.output(self.decide('pip install toolkit'))
                self.assertEqual(out['permissionDecision'], 'ask')
                reason = out['permissionDecisionReason']
                self.assertIn('CAUTION', reason)
                self.assertIn('development folders', reason)
                self.assertIn('scripts/', reason)
        self.assertEqual(len([u for u in self.fake.requests if u.endswith('.tar.gz')]), 1)

    def test_the_same_code_in_the_package_still_blocks(self):
        self.sdist('toolkit2', {'toolkit2/__init__.py': self.RISKY, 'scripts/bench.py': self.RISKY})
        out = self.output(self.decide('pip install toolkit2'))
        self.assertEqual(out['permissionDecision'], 'deny')

    def test_wheels_are_not_given_the_development_folder_allowance(self):
        self.fake.pypi('whl', '1.0', [('whl-1.0-py3-none-any.whl', wheel({'scripts/bench.py': self.RISKY}),
                                       'bdist_wheel')])
        self.assertEqual(self.output(self.decide('pip install whl'))['permissionDecision'], 'deny')

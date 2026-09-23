"""Regressions for source binding and repeated scans, using real scanner workers."""
import json
import os
from pathlib import Path
from unittest.mock import patch

from tests.test_gate import GateTestCase
from tests.gate_fixtures import tgz, wheel
from trojaino import gate, registry
from trojaino.install_detect import detect


class InstallIntegrityTests(GateTestCase):
    def setUp(self):
        super().setUp()
        self.fake.npm('good', {'1.0.0': tgz({'index.js':'1'})})
        self.fake.npm('native', {'1.0.0': tgz({'index.js':'1','addon.node':b'\x7fELF'})})

    def test_compiled_warning_survives_a_declined_first_attempt(self):
        for _ in range(2):
            out = self.output(self.decide('npm install native'))
            self.assertEqual(out['permissionDecision'], 'ask')
            self.assertIn('compiled code', out['permissionDecisionReason'])
        self.assertEqual(len([u for u in self.fake.requests if u.endswith('.tgz')]),1)

    def test_old_cache_records_are_not_used(self):
        self.decide('npm install native')
        path = next((Path(self.home.name)/'state/verdicts').glob('*.json'))
        data = json.loads(path.read_text())
        del data['compiled']
        path.write_text(json.dumps(data))
        self.assertEqual(self.output(self.decide('npm install native'))['permissionDecision'], 'ask')
        self.assertEqual(len([u for u in self.fake.requests if u.endswith('.tgz')]),2)

    def test_repeated_package_options_scan_and_pin_every_named_package(self):
        out = self.output(self.decide('npx --package good --package native good'))
        self.assertEqual(out['permissionDecision'], 'ask')
        self.assertIn('compiled code', out['permissionDecisionReason'])
        self.fake.npm('other', {'2.0.0': tgz({'index.js':'1'})})
        out = self.output(self.decide('npx --package=good -p other good'))
        self.assertEqual(out['updatedInput']['command'], 'npx --package=good@1.0.0 -p other@2.0.0 good')

    def test_custom_registry_forms_never_get_public_clearance(self):
        commands = ['NPM_CONFIG_REGISTRY=https://private.example npm install good',
                    'npm --registry https://private.example install good',
                    'npm --registry=https://private.example install good',
                    'npm install --userconfig custom.npmrc good']
        for command in commands:
            with self.subTest(command=command):
                self.assertEqual(self.output(self.decide(command))['permissionDecision'],'ask')
        with patch.dict(os.environ, {'NPM_CONFIG_REGISTRY':'https://private.example'}):
            self.assertEqual(self.output(self.decide('npm install good'))['permissionDecision'],'ask')
        self.assertFalse(self.fake.requests)

    def test_project_registry_configuration_needs_review_without_leaking_secrets(self):
        folder = Path(self.home.name)/'project'
        folder.mkdir()
        (folder/'.npmrc').write_text('registry=https://secret-token@private.example\n')
        out = self.output(self.decide('npm install good',cwd=str(folder)))
        self.assertEqual(out['permissionDecision'],'ask')
        self.assertNotIn('secret-token', json.dumps(out))
        self.assertFalse(self.fake.requests)

    def test_source_archive_override_is_not_cleared_by_a_wheel_scan(self):
        self.fake.pypi('pkg','1.0', [('pkg-1.0-py3-none-any.whl',wheel({'pkg.py':'1'}),'bdist_wheel')])
        out = self.output(self.decide('pip install --no-binary=:all: pkg'))
        self.assertEqual(out['permissionDecision'],'ask')
        self.assertFalse(self.fake.requests)
        out = self.output(self.decide('pip install pkg'))
        artifact = registry.resolve_pypi('pkg',None)
        self.assertEqual(out['updatedInput']['command'],
                         "pip install 'pkg @ " + artifact.url + '#sha256=' + artifact.digest[7:] + "'")

    def test_uvx_equals_from_uses_actual_distribution(self):
        self.fake.pypi('dist','1.0', [('dist-1.0-py3-none-any.whl',wheel({'dist.py':'1'}),'bdist_wheel')])
        out = self.output(self.decide('uvx --from=dist program'))
        self.assertNotIn('permissionDecision',out)
        self.assertEqual(out['updatedInput']['command'], 'uvx --from=dist==1.0 program')

    def test_unbound_nested_and_github_forms_ask_after_scanning(self):
        sha='a'*40
        self.fake.github('o/r', {'HEAD':sha}, {sha:tgz({'index.js':'1'},root='r')})
        for command in ['bash -c "npx good"','git clone https://github.com/o/r.git',
                        'gh repo clone https://github.com/o/r']:
            with self.subTest(command=command):
                out=self.output(self.decide(command))
                self.assertEqual(out['permissionDecision'],'ask')
                self.assertIn('cannot be bound',out['permissionDecisionReason'])
                self.assertNotIn('updatedInput',out)

    def test_detection_preserves_equals_from_and_global_options(self):
        self.assertEqual(detect('uvx --from=dist program')[0].targets[0].name,'dist')
        self.assertEqual(detect('npm --prefix project install good')[0].targets[0].name,'good')
        self.assertEqual(detect('gh repo clone https://github.com/o/r')[0].targets[0].name,'o/r')

    def test_replacement_metadata_is_one_shell_argument(self):
        import shlex
        from trojaino.install_detect import Token
        value = "pkg @ https://files.pythonhosted.org/a'b;echo-file.whl#sha256=abc"
        for quoted in ("", "'", '"'):
            token = Token('pkg',0,3,quoted,True)
            self.assertEqual(shlex.split(gate._quote(value,token,'Bash')),[value])
            self.assertEqual(gate._quote(value,token,'PowerShell'), "'" + value.replace("'","''") + "'")

    def test_config_mutation_and_additional_runner_packages_require_review(self):
        for command in ('npm config set registry https://private.example && npm install good',
                        'uv run --with=good program'):
            with self.subTest(command=command):
                self.assertEqual(self.output(self.decide(command))['permissionDecision'],'ask')

    def test_local_runner_and_python_module_option_forms_are_recognized(self):
        self.assertEqual(detect('npx ./local-tool')[0].targets[0].ecosystem,'local')
        self.assertEqual(detect('python -m pip --isolated install good')[0].targets[0].name,'good')

    def test_global_install_prefix_does_not_disable_clean_scans(self):
        prefix=Path(self.home.name)/'prefix'
        (prefix/'etc').mkdir(parents=True)
        with patch.dict(os.environ, {'NPM_CONFIG_PREFIX':str(prefix),'PNPM_HOME':str(prefix),'YARN_CACHE_FOLDER':str(prefix)}):
            self.assertNotIn('permissionDecision',self.output(self.decide('npm install good')))
            (prefix/'etc/npmrc').write_text('registry=https://private.example\n')
            self.assertEqual(self.output(self.decide('npm install good'))['permissionDecision'],'ask')

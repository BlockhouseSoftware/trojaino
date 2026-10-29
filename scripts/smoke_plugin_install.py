"""Exercise Claude's plugin manager and installed hooks without a model session.

--public checks the real release catalog. The default installs a generated
candidate through a git marketplace and tests an old-to-new catalog update.
All Claude configuration, caches and reports live in a temporary directory.
"""
from __future__ import annotations
import argparse
import json
import os
import re
from pathlib import Path
import shutil
import subprocess
import tempfile
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from trojaino.doctor import doctor_argv  # noqa: E402


def run(*args, cwd=None, env=None):
    print('COMMAND', json.dumps(list(args)), flush=True)
    result = subprocess.run(list(args), cwd=cwd, env=env, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stdout[-2000:]} {result.stderr[-2000:]}')
    return result.stdout


def check_doctor(root, env, expected_status):
    """Require the expected diagnosis and byte-for-byte settings preservation."""
    settings = Path(env['CLAUDE_CONFIG_DIR']) / 'settings.json'
    before = settings.read_bytes()
    argv = doctor_argv(root)
    print('COMMAND', json.dumps(argv), flush=True)
    result = subprocess.run(argv, cwd=settings.anchor, env=env,
                            text=True, capture_output=True, timeout=90)
    print(result.stdout.strip(), flush=True)
    assert settings.read_bytes() == before, 'doctor mutated settings'
    diagnosis = json.loads(result.stdout)
    assert result.returncode == (0 if expected_status == 'Ready' else 1), (result, diagnosis)
    assert diagnosis['status'] == expected_status, diagnosis
    return diagnosis


def check_manager_state(env, enabled, unrelated):
    """Read back manager effects, excluding only the target enablement key."""
    identity = 'trojaino@blockhouse-software'
    config = Path(env['CLAUDE_CONFIG_DIR'])
    registered = json.loads((config/'plugins/installed_plugins.json').read_text())['plugins']
    settings = json.loads((config/'settings.json').read_text())
    states = settings.get('enabledPlugins', {})
    if enabled is None:
        assert identity not in registered, registered
        assert identity not in states, states
    else:
        assert any(e['scope'] == 'user' for e in registered[identity]), registered
        assert states.get(identity) is enabled, states
    states.pop(identity, None)
    assert settings == unrelated, 'manager changed unrelated settings'


def verify(env, version):
    config = Path(env['CLAUDE_CONFIG_DIR'])
    entries = json.loads((config/'plugins/installed_plugins.json').read_text())['plugins']['trojaino@blockhouse-software']
    current = next(e for e in entries if e['scope'] == 'user')
    assert current['version'] == version, current
    settings = json.loads((config/'settings.json').read_text())
    assert settings['enabledPlugins']['trojaino@blockhouse-software'] is True
    entry = Path(current['installPath'])/'scripts/preflight.py'
    answer = check_doctor(entry.parent.parent, env, 'Ready')
    assert answer['status'] == 'Ready', answer
    assert answer['version'] == version
    assert all(c['ok'] for c in answer['checks']), answer
    print('PASS installed version, enabled state, integrity, registration and actual hooks:',version)
    return entry


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    source = parser.add_mutually_exclusive_group()
    source.add_argument('--public',action='store_true')
    source.add_argument('--candidate-git',action='store_true', help='install the pushed candidate through the production git-subdir source type')
    parser.add_argument('--expected-version')
    args=parser.parse_args()
    version=args.expected_version or json.loads((ROOT/'plugins/trojaino/.claude-plugin/plugin.json').read_text())['version']
    with tempfile.TemporaryDirectory(prefix='trojaino-install-smoke-') as tmp:
        base=Path(tmp)
        claude=shutil.which('claude') or 'claude'
        # Do not inherit auth/provider variables or discover the invoking project.
        env={key: os.environ[key] for key in (
            'PATH', 'SystemRoot', 'WINDIR', 'COMSPEC', 'PATHEXT',
            'ProgramFiles', 'ProgramFiles(x86)', 'CLAUDE_CODE_GIT_BASH_PATH'
        ) if key in os.environ}
        for name in ('claude', 'home', 'state', 'local', 'tmp', 'config', 'cache'):
            (base/name).mkdir()
        env.update(CLAUDE_CONFIG_DIR=str(base/'claude'), HOME=str(base/'home'),
                   USERPROFILE=str(base/'home'), XDG_STATE_HOME=str(base/'state'),
                   XDG_CONFIG_HOME=str(base/'config'), XDG_CACHE_HOME=str(base/'cache'),
                   LOCALAPPDATA=str(base/'local'), APPDATA=str(base/'config'),
                   TMPDIR=str(base/'tmp'), TMP=str(base/'tmp'), TEMP=str(base/'tmp'),
                   CLAUDE_CODE_DISABLE_NONESSENTIAL_TRAFFIC='1')
        print('ISOLATED CLAUDE_CONFIG_DIR', env['CLAUDE_CONFIG_DIR'], flush=True)
        unrelated={'permissions': {'deny': ['Read(./smoke-private/**)']},
                   'enabledPlugins': {'unrelated@smoke-fixture': False}}
        settings=base/'claude/settings.json'
        settings.write_text(json.dumps(unrelated), encoding='utf-8')
        def plugin(*words):
            print(run(claude,'plugin',*words,cwd=base.anchor,env=env).strip())
        if args.public:
            plugin('marketplace','add','BlockhouseSoftware/claude-marketplace')
            plugin('install','trojaino@blockhouse-software','--scope','user')
        elif args.candidate_git:
            sha = os.environ.get('TROJAINO_CANDIDATE_SHA') or run('git','rev-parse','HEAD',cwd=ROOT).strip()
            if not re.fullmatch('[0-9a-f]{40}',sha):
                raise ValueError('candidate must be a full commit SHA')
            market=base/'catalog'
            (market/'.claude-plugin').mkdir(parents=True)
            (market/'.claude-plugin/marketplace.json').write_text(json.dumps({
                'name':'blockhouse-software','owner':{'name':'ci'},
                'plugins':[{'name':'trojaino','source':{'source':'git-subdir',
                    'url':'https://github.com/BlockhouseSoftware/trojaino.git',
                    'path':'plugins/trojaino','sha':sha}}]}),encoding='utf-8')
            plugin('marketplace','add',str(market))
            plugin('install','trojaino@blockhouse-software','--scope','user')
        else:
            market=base/'market'
            (market/'.claude-plugin').mkdir(parents=True)
            shutil.copytree(ROOT/'plugins/trojaino',market/'trojaino')
            (market/'.claude-plugin/marketplace.json').write_text(json.dumps({'name':'blockhouse-software',
                'owner':{'name':'ci'},'plugins':[{'name':'trojaino','source':'./trojaino'}]}))
            manifest=market/'trojaino/.claude-plugin/plugin.json'
            original=manifest.read_bytes()
            old=json.loads(original);old['version']='0.3.0'
            manifest.write_bytes(json.dumps(old).encode())
            run('git','init',str(market))
            def commit(message):
                run('git','add','.',cwd=market)
                run('git','-c','user.name=Plugin smoke','-c','user.email=smoke@example.invalid',
                    'commit','-m',message,cwd=market)
            commit('previous catalog fixture')
            plugin('marketplace','add',str(market))
            plugin('install','trojaino@blockhouse-software','--scope','user')
            installed=json.loads((base/'claude/plugins/installed_plugins.json').read_text())
            assert installed['plugins']['trojaino@blockhouse-software'][0]['version']=='0.3.0'
            manifest.write_bytes(original)
            commit('candidate release')
            plugin('marketplace','update','blockhouse-software')
            plugin('update','trojaino@blockhouse-software')
        entry=verify(env,version)
        # Marketplace add legitimately records its source in user settings.
        # Check seeded preferences survived, then snapshot the full installed state.
        installed_settings=json.loads(settings.read_text())
        assert installed_settings['permissions'] == unrelated['permissions']
        assert installed_settings['enabledPlugins']['unrelated@smoke-fixture'] is False
        unrelated=installed_settings
        unrelated['enabledPlugins'].pop('trojaino@blockhouse-software')
        check_manager_state(env, True, unrelated)
        plugin('disable','trojaino@blockhouse-software','--scope','user')
        check_manager_state(env, False, unrelated)
        diagnosis=check_doctor(entry.parent.parent, env, 'Needs attention')
        assert any('not enabled' in a for a in diagnosis['actions']), diagnosis
        print('PASS manager disable: Needs attention; unrelated settings and doctor bytes preserved')
        plugin('enable','trojaino@blockhouse-software','--scope','user')
        check_manager_state(env, True, unrelated)
        verify(env,version)
        print('PASS manager enable: Ready; unrelated settings and doctor bytes preserved')
        # Legacy prepared hooks must be diagnosed without deleting them.
        settings=base/'claude/settings.json'
        data=json.loads(settings.read_text())
        data['hooks']={'PreToolUse':[{'hooks':[{'type':'command','command':'old-trojaino-prepared-hook'}]}]}
        settings.write_text(json.dumps(data))
        diagnosis=check_doctor(entry.parent.parent, env, 'Needs attention')
        assert any('Legacy Trojaino' in a for a in diagnosis['actions']), diagnosis
        assert json.loads(settings.read_text()) == data
        print('PASS legacy hook migration diagnosis preserves settings')
        # Integrity errors must not report Ready.
        manifest=entry.parent.parent/'.claude-plugin/plugin.json'
        manifest.write_text(manifest.read_text()+'\n')
        diagnosis=check_doctor(entry.parent.parent, env, 'Needs attention')
        assert any(not c['ok'] for c in diagnosis['checks'] if c['check']=='Packaged file integrity')
        print('PASS damaged payload is not Ready')
        # Keep deliberate legacy settings: uninstall must preserve them too.
        unrelated['hooks']=data['hooks']
        plugin('uninstall','trojaino@blockhouse-software','--scope','user')
        check_manager_state(env, None, unrelated)
        print('PASS manager uninstall: registration absent; unrelated settings preserved')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

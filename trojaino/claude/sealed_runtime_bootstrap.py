"""Template embedded by build_sealed_runtime.py; never loaded from disk at runtime.

The approved interpreter and generated entry script are trust anchors. Runtime
modules and worker bootstraps execute from the captured image, not filesystem
paths. A digest passed by the parent binds each worker's input capsule.
"""
import hashlib
import importlib.abc
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import tempfile
import threading
import sys
from types import MappingProxyType

if sys.version_info < (3, 11) or not sys.flags.isolated or not sys.flags.no_site:
    print(json.dumps({'decision': 'deny', 'reason': 'isolated_python_required'}))
    raise SystemExit(2)

_CAPSULE: dict = globals()['_CAPSULE']
_sources = MappingProxyType(dict(_CAPSULE['sources']))
_version = _CAPSULE['version']
_entry = _CAPSULE['entry']
_bootstrap = _CAPSULE['bootstrap']
_identity = hashlib.sha256(json.dumps([_version, _bootstrap, dict(_sources)], sort_keys=True).encode()).hexdigest()

class ImageLoader(importlib.abc.MetaPathFinder, importlib.abc.Loader):
    def find_spec(self, fullname, path=None, target=None):
        if fullname == 'trojaino' or fullname.startswith('trojaino.'):
            if fullname not in _sources:
                raise ModuleNotFoundError('module absent from sealed runtime: ' + fullname)
            return importlib.util.spec_from_loader(fullname, self, is_package=any(n.startswith(fullname + '.') for n in _sources))
        return None

    def create_module(self, spec):
        return None

    def exec_module(self, module):
        module.__file__ = '<sealed>/' + module.__name__.replace('.', '/') + '.py'
        if module.__name__ == 'trojaino':
            module.__path__ = []
        exec(compile(_sources[module.__name__], module.__file__, 'exec'), module.__dict__)

for _name in list(sys.modules):
    if _name == 'trojaino' or _name.startswith('trojaino.'):
        del sys.modules[_name]
sys.meta_path.insert(0, ImageLoader())
sys.dont_write_bytecode = True

# This constant consumes a bounded capsule, verifies BEFORE executing any of its
# code, and never reads the entry script or runtime modules from disk.
_CHILD = "import sys,json,hashlib; b=sys.stdin.buffer.readline(2000002); valid=len(b)<=2000001 and b.endswith(b'\\n') and hashlib.sha256(b[:-1]).hexdigest()==sys.argv[1]; valid or sys.exit(2); _CAPSULE=json.loads(b); exec(compile(_CAPSULE['bootstrap'],'<sealed-bootstrap>','exec'))"

def image_worker(name, args, timeout=20, stdin=None):
    from trojaino.preflight import trusted_environment
    capsule = {'sources': dict(_sources), 'version': _version, 'entry': _entry,
               'bootstrap': _bootstrap, 'operation': name, 'args': args}
    data = json.dumps(capsule, sort_keys=True).encode()
    if len(data) > 2000000:
        raise ValueError('worker image limit')
    argv = [sys.executable, '-I', '-S', '-c', _CHILD, hashlib.sha256(data).hexdigest()]
    environment = trusted_environment()
    if 'TROJAINO_NODE' in os.environ:
        environment['TROJAINO_NODE'] = os.environ['TROJAINO_NODE']
    with tempfile.TemporaryFile() as output:
        process = subprocess.Popen(argv, stdin=subprocess.PIPE, stdout=output,
            stderr=subprocess.DEVNULL, cwd=str(Path(sys.executable).parent), env=environment)
        def feed():
            try:
                process.stdin.write(data + b'\n')
                process.stdin.flush()
                if name == 'hook_input' and stdin is not None:
                    total = 0
                    while total < 65537:
                        block = os.read(stdin.fileno(), 65537 - total)
                        if not block:
                            break
                        total += len(block)
                        process.stdin.write(block)
                        process.stdin.flush()
            except (OSError, ValueError):
                pass  # An incomplete event or capsule is denied by the child.
            finally:
                try:
                    process.stdin.close()
                except (OSError, ValueError):
                    pass
        threading.Thread(target=feed, daemon=True).start()
        try:
            status = process.wait(timeout=timeout)
            if status:
                raise subprocess.CalledProcessError(status, argv)
        finally:
            if process.poll() is None:
                process.kill()
                process.wait()
        output.seek(0)
        result = output.read(5000001)
    if len(result) > 5000000:
        raise ValueError('worker output limit')
    return json.loads(result)

import trojaino
# Metadata comes only from the captured build image, never interpreter-adjacent
# pyproject.toml or installed distribution metadata.
trojaino.__version__ = _version
setattr(trojaino, '_sealed_identity', _identity)
setattr(trojaino, '_sealed_entry', _entry)
setattr(trojaino, '_sealed_worker', image_worker)

_operation = _CAPSULE.get('operation')
if _operation:
    _job = None
    if os.name == 'nt':
        from trojaino.preflight_windows import contain_process
        _job = contain_process()
    from trojaino import preflight
    if _operation == 'scan_path':
        from trojaino.scanner import scan_path, ScanLimits
        _result = scan_path(_CAPSULE['args'][0], profile='default',
                            limits=ScanLimits(max_elapsed_seconds=8)).to_dict()
    elif _operation == 'hook_input':
        _result = preflight.hook_input()
    elif _operation in {'_gate', 'launch_plan', 'scanner_identity'}:
        _result = getattr(preflight, _operation)(*_CAPSULE['args'])
    else:
        raise ValueError('unsupported image operation')
    print(json.dumps(_result, ensure_ascii=True))
else:
    from trojaino.preflight import main
    raise SystemExit(main())

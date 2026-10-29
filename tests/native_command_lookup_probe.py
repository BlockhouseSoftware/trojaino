"""Bounded native command-discovery experiment; emits observations, not PASS."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import time


def main():
    if os.name != 'nt':
        raise SystemExit('Windows-only diagnostic')
    shell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    with tempfile.TemporaryDirectory(prefix='trojaino-lookup-probe-') as tmp:
        env = dict(os.environ, PATH=tmp)
        cases = {
            'application-lookup': '$c=Get-Command python3.exe -CommandType Application -ErrorAction SilentlyContinue',
            'lookup-without-module-autoload': "$PSModuleAutoLoadingPreference='None'; $c=Get-Command python3.exe -CommandType Application -ErrorAction SilentlyContinue",
            'list-imported-lookup': '$c=Get-Command python3.exe -CommandType Application -ListImported -ErrorAction SilentlyContinue',
            'engine-lookup': "$c=$ExecutionContext.InvokeCommand.GetCommand('python3.exe',[System.Management.Automation.CommandTypes]::Application)",
            'literal-path-enumeration': "$c=$false; foreach($p in ($env:PATH -split ';')) { if($p -and [IO.File]::Exists([IO.Path]::Combine($p,'python3.exe'))) {$c=$true; break} }",
        }
        for present in (False, True):
            if present:
                shutil.copy2(sys.executable, Path(tmp) / 'python3.exe')
            for label, lookup in cases.items():
                # Console calls cannot autoload Utility and confound the probe.
                script = "[Console]::WriteLine('PROBE before lookup'); " + lookup + "; [Console]::WriteLine('PROBE after lookup found=' + [bool]$c)"
                started = time.monotonic()
                try:
                    result = subprocess.run([shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                                            env=env, input='', capture_output=True, text=True, timeout=12)
                    record = {'case': label, 'present': present, 'exit': result.returncode, 'stdout': result.stdout[-1500:],
                              'stderr': result.stderr[-1500:], 'timed_out': False}
                except subprocess.TimeoutExpired as exc:
                    stdout = exc.stdout or b''
                    stderr = exc.stderr or b''
                    record = {'case': label, 'present': present, 'timed_out': True,
                              'stdout': stdout.decode(errors='replace')[-1500:] if isinstance(stdout, bytes) else stdout[-1500:],
                              'stderr': stderr.decode(errors='replace')[-1500:] if isinstance(stderr, bytes) else stderr[-1500:]}
                record['seconds'] = round(time.monotonic() - started, 3)
                print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()

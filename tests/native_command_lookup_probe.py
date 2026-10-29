"""Bounded native command-discovery experiment; emits observations, not PASS."""
import json
import os
from pathlib import Path
import subprocess
import tempfile
import time


def main():
    if os.name != 'nt':
        raise SystemExit('Windows-only diagnostic')
    shell = str(Path(os.environ['SystemRoot']) / 'System32/WindowsPowerShell/v1.0/powershell.exe')
    with tempfile.TemporaryDirectory(prefix='trojaino-lookup-probe-') as tmp:
        env = dict(os.environ, PATH=tmp)
        cases = {
            'startup-only': "Write-Output 'PROBE started'; Write-Output 'PROBE finished'",
            'application-lookup': "Write-Output 'PROBE before lookup'; $c=Get-Command python3.exe -CommandType Application -ErrorAction SilentlyContinue; Write-Output ('PROBE after lookup found=' + [bool]$c)",
            'lookup-without-module-autoload': "$PSModuleAutoLoadingPreference='None'; Write-Output 'PROBE before lookup'; $c=Get-Command python3.exe -CommandType Application -ErrorAction SilentlyContinue; Write-Output ('PROBE after lookup found=' + [bool]$c)",
            'literal-path-enumeration': "Write-Output 'PROBE before literal'; $found=$false; foreach($p in ($env:PATH -split ';')) { if($p -and [IO.File]::Exists([IO.Path]::Combine($p,'python3.exe'))) {$found=$true; break} }; Write-Output ('PROBE after literal found=' + $found)",
        }
        for label, script in cases.items():
            started = time.monotonic()
            try:
                result = subprocess.run([shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-Command', script],
                                        env=env, input='', capture_output=True, text=True, timeout=12)
                record = {'case': label, 'exit': result.returncode, 'stdout': result.stdout[-1500:],
                          'stderr': result.stderr[-1500:], 'timed_out': False}
            except subprocess.TimeoutExpired as exc:
                stdout = exc.stdout or b''
                stderr = exc.stderr or b''
                record = {'case': label, 'timed_out': True,
                          'stdout': stdout.decode(errors='replace')[-1500:] if isinstance(stdout, bytes) else stdout[-1500:],
                          'stderr': stderr.decode(errors='replace')[-1500:] if isinstance(stderr, bytes) else stderr[-1500:]}
            record['seconds'] = round(time.monotonic() - started, 3)
            print(json.dumps(record), flush=True)


if __name__ == '__main__':
    main()

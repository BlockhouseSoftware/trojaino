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
            'scoped-lookup': "$c = & { $PSModuleAutoLoadingPreference='None'; [Console]::Error.WriteLine('PROBE inside scope'); Get-Command python3.exe -CommandType Application -ErrorAction SilentlyContinue } | Select-Object -First 1",
            'scoped-two-names': "foreach($name in @('python3.exe','python.exe')) { [Console]::Error.WriteLine('PROBE before '+$name); $c = & { $PSModuleAutoLoadingPreference='None'; Get-Command $name -CommandType Application -ErrorAction SilentlyContinue } | Select-Object -First 1; [Console]::Error.WriteLine('PROBE after '+$name) }",
            'save-and-restore': "$saved=$PSModuleAutoLoadingPreference; try { $PSModuleAutoLoadingPreference='None'; $c=Get-Command python3.exe -CommandType Application -ErrorAction SilentlyContinue } finally { $PSModuleAutoLoadingPreference=$saved }; $c=$c | Select-Object -First 1; @{diagnostic='JSON works'} | ConvertTo-Json -Compress",
            'literal-path-enumeration': "$c=$false; foreach($p in ($env:PATH -split ';')) { if($p -and [IO.File]::Exists([IO.Path]::Combine($p,'python3.exe'))) {$c=$true; break} }",
        }
        traced = (Path(__file__).resolve().parents[1] / 'plugins/trojaino/scripts/launch.ps1').read_text()
        traced = traced.replace("foreach ($name", "[Console]::Error.WriteLine('PROBE before loop')\nforeach ($name")
        traced = traced.replace('        Get-Command $name', "        [Console]::Error.WriteLine('PROBE lookup ' + $name)\n        Get-Command $name")
        traced = traced.replace('    if (-not $candidate)', "    [Console]::Error.WriteLine('PROBE lookup returned ' + $name)\n    if (-not $candidate)")
        traced = traced.replace("\nif ($Mode -eq 'doctor') {", "\n[Console]::Error.WriteLine('PROBE before diagnostic JSON')\nif ($Mode -eq 'doctor') {")
        traced_file = Path(tmp) / 'trace.ps1'
        traced_file.write_text(traced)
        try:
            result = subprocess.run([shell, '-NoLogo', '-NoProfile', '-NonInteractive', '-File', str(traced_file), 'doctor'], env=env, input='', capture_output=True, text=True, timeout=12)
            print(json.dumps({'case':'actual-launcher-trace','exit':result.returncode,'stdout':result.stdout,'stderr':result.stderr}), flush=True)
        except subprocess.TimeoutExpired as exc:
            print(json.dumps({'case':'actual-launcher-trace','timed_out':True,'stdout':str(exc.stdout),'stderr':str(exc.stderr)}), flush=True)
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

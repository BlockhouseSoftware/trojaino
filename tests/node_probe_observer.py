"""TEST ONLY: observe the original POSIX probe through the shipped CLI.

Run with trusted Python -I -S. No production imports of this helper, runtime
hooks, retries, stream redirection, or changes to subprocess arguments. The
sidecar contains metadata only, not environment values or exception messages.
"""
import json
from pathlib import Path
import runpy
import subprocess
import sys
import time
from unittest.mock import patch


def main():
    destination = Path(sys.argv[1])
    cli = Path(__file__).resolve().parents[1] / "plugins/trojaino/scripts/preflight.py"
    sys.argv = [str(cli), *sys.argv[2:]]
    real_run = subprocess.run

    def observe(argv, **kwargs):
        if "--permission" not in argv or "--eval" not in argv:
            return real_run(argv, **kwargs)
        record = {"argv": argv, "cwd": kwargs.get("cwd"),
                  "timeout": kwargs.get("timeout"), "check": kwargs.get("check"),
                  "stdio": [kwargs.get(key) for key in ("stdin", "stdout", "stderr")],
                  "env_keys": sorted(kwargs.get("env", {}))}
        start = time.monotonic()
        try:
            completed = real_run(argv, **kwargs)
            record["returncode"] = completed.returncode
            return completed
        except (OSError, subprocess.SubprocessError) as error:
            record.update(exception=type(error).__name__,
                          returncode=getattr(error, "returncode", None),
                          errno=getattr(error, "errno", None))
            raise
        finally:
            record["elapsed_seconds"] = time.monotonic() - start
            try:
                destination.write_text(json.dumps(record, ensure_ascii=True))
            except OSError:
                # Never replace the original result/exception with observer I/O.
                # The calling test separately requires the sidecar to exist.
                pass

    with patch.object(subprocess, "run", observe):
        # Execute the actual isolated CLI, including its trusted import setup,
        # receipt revalidation, launch watchdog and exec path; not main/plan alone.
        runpy.run_path(str(cli), run_name="__main__")


if __name__ == "__main__":
    main()

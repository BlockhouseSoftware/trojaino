"""Trusted worker entry; never imports candidate code or inherits Python hooks."""
import json
import os
import sys


def main():
    # The child owns the job: killing this worker closes its only job handle,
    # killing scanner descendants too. No children are started before assignment.
    job = None
    if os.name == 'nt':
        from trojaino.preflight_windows import contain_process
        job = contain_process()
    try:
        from trojaino import preflight
        name, args = json.loads(sys.argv[1])
        if name not in {'_gate', 'launch_plan', 'hook_input', 'scanner_identity'}:
            raise ValueError('unsupported worker operation')
        result = getattr(preflight, name)(*args)
        print(json.dumps(result, ensure_ascii=True), flush=True)
    finally:
        # Job intentionally lives until process exit (closing would kill self).
        _ = job


if __name__ == '__main__':
    main()

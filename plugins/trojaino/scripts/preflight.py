"""Invoke only with an explicitly trusted Python 3.11+ and -I -S."""
import sys
from pathlib import Path

if sys.version_info < (3, 11):
    print('{"decision":"deny","reason":"Python 3.11+ required"}')
    raise SystemExit(2)

# Deliberately in-place plugin: trusted repo, never target cwd or PYTHONPATH.
sys.path.insert(0, str(Path(__file__).resolve().parents[3]))
from trojaino.preflight import main

if __name__ == "__main__":
    raise SystemExit(main())

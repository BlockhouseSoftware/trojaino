"""Render the sealed scanner image. Implementation: trojaino.claude.seal.

Retained so release tooling, CI and the native setup build keep one entry point
while the renderer itself ships inside the installable package.
"""
import argparse
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trojaino.claude.seal import BOOTSTRAP, PACKAGE, build, render, source_map, version  # noqa: E402,F401

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('output', type=Path)
    build(parser.parse_args().output)

"""Regenerate plugins/trojaino from the canonical packaged payload.

plugins/trojaino is a build artifact, like the sealed entry inside it. Edit
trojaino/claude/payload instead; a test fails if the two disagree.
"""
import argparse
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

from trojaino.claude.payload import marketplace_files  # noqa: E402


def generate(plugin_dir: Path) -> list[str]:
    written = []
    for name, data in sorted(marketplace_files().items()):
        target = plugin_dir / name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists() or target.read_bytes() != data:
            target.write_bytes(data)
            written.append(name)
    return written


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('plugin_dir', nargs='?', type=Path, default=ROOT / 'plugins/trojaino')
    changed = generate(parser.parse_args().plugin_dir)
    print('updated: ' + (', '.join(changed) if changed else 'nothing (already current)'))

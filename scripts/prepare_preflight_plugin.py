"""Prepare a NEW private layout from reviewed source. Implementation: trojaino.claude.prepare."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trojaino.claude.prepare import (  # noqa: E402,F401
    ROOT, bind_sealed_entry, coverage_section, plan, prepare, prepared_hook_manifest,
)

if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('destination')
    parser.add_argument('--personal-plugin-name', help='Create a disabled plugin directly at the new final destination; use a new trojaino-local- identity for each version. Does not enable it or modify settings.')
    parser.add_argument('--plan', action='store_true', help='Render a disabled personal plugin as a ZIP to stdout without creating its final directory. For the reviewed native controller only; not an installer or activation.')
    args = parser.parse_args()
    if args.plan:
        sys.stdout.buffer.write(plan(args.destination, args.personal_plugin_name))
    else:
        print(json.dumps(prepare(args.destination, args.personal_plugin_name)))

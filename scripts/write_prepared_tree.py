"""Write new prepared bytes via pinned parents. Implementation: trojaino.claude.writer."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from trojaino.claude.writer import write_tree  # noqa: E402,F401

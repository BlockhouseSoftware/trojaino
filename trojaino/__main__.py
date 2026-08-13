"""Run Trojaino without installing a console-script entry point."""

from aishield.cli import main


if __name__ == "__main__":
    raise SystemExit(main())

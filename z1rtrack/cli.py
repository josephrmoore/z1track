"""Console entry point: `python -m z1rtrack.cli`."""

import sys

from .service import run_cli


def main() -> int:
    return run_cli(sys.argv[1:]) or 0


if __name__ == "__main__":
    sys.exit(main())
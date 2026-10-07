"""Start the VoxBridge desktop application."""

from pathlib import Path
import sys


SOURCE_DIR = Path(__file__).resolve().parent / "src"


def main() -> None:
    sys.path.insert(0, str(SOURCE_DIR))
    from voxbridge.ui import run_app

    run_app()


if __name__ == "__main__":
    main()

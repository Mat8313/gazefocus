"""Point d'entrée : lance gazefocus dans la zone de notification."""
import argparse
import sys

from . import tray, winfocus
from .decision import Settings


def main():
    parser = argparse.ArgumentParser(prog="gazefocus", description=__doc__)
    parser.add_argument("--camera", type=int, default=0, help="index de la webcam")
    parser.add_argument("--dwell", type=float, default=Settings.dwell,
                        help="secondes à fixer un écran avant de basculer")
    args = parser.parse_args()

    if not winfocus.acquire_single_instance():
        sys.exit(0)
    winfocus.enable_dpi_awareness()
    tray.run(args.camera, Settings(dwell=args.dwell))


if __name__ == "__main__":
    main()

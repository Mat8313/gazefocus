"""Point d'entrée : lance gazefocus dans la zone de notification."""
import sys

from . import config, log, tray, winfocus


def main():
    if not winfocus.acquire_single_instance():
        sys.exit(0)
    log.setup()
    log.log.info("démarrage")
    winfocus.enable_dpi_awareness()
    tray.run(config.load())


if __name__ == "__main__":
    main()

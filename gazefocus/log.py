"""Journal dans %APPDATA%\\gazefocus\\gazefocus.log.

L'exe n'a pas de console : sans ce fichier, une erreur ne laisse aucune trace.
Par respect de la vie privée, on n'y écrit ni titres de fenêtres, ni noms
d'applications, ni poses mesurées.
"""
import logging
import sys
import threading
from logging.handlers import RotatingFileHandler

from .config import DATA_DIR

LOG_PATH = DATA_DIR / "gazefocus.log"
log = logging.getLogger("gazefocus")


def setup():
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    # Deux fichiers de 300 ko au plus : le journal ne grossit jamais indéfiniment.
    handler = RotatingFileHandler(LOG_PATH, maxBytes=300_000, backupCount=1, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)s %(message)s"))
    log.addHandler(handler)
    log.setLevel(logging.INFO)

    def on_crash(kind, error, traceback):
        log.critical("Erreur non rattrapée", exc_info=(kind, error, traceback))

    sys.excepthook = on_crash
    threading.excepthook = lambda args: on_crash(
        args.exc_type, args.exc_value, args.exc_traceback
    )

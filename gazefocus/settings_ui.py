"""Fenêtre de réglages (tkinter), ouverte depuis le menu de l'icône."""
import threading
import tkinter as tk
from tkinter import ttk

from . import config as config_module
from .config import Config

_open = threading.Lock()

DELAYS = (
    ("dwell", "Temps de fixation avant bascule (s)", 0.1, 2.0),
    ("typing_cooldown", "Garder le focus après une frappe (s)", 0.0, 15.0),
    ("mouse_cooldown", "Garder le focus après la souris (s)", 0.0, 10.0),
)
OPTIONS = (
    ("learn_from_clicks", "Affiner la calibration à chaque clic"),
    ("move_cursor", "Amener le curseur sur la fenêtre choisie"),
    ("use_eyes", "Tenir compte des yeux, pas seulement de la tête (expérimental)"),
    ("same_screen", "Basculer aussi entre fenêtres d'un même écran (expérimental)"),
)


def show(current: Config, on_save):
    """Ouvre la fenêtre dans son propre thread ; une seule à la fois."""
    if _open.acquire(blocking=False):
        threading.Thread(target=_run, args=(current, on_save), daemon=True).start()


def _run(current, on_save):
    # Tout objet Tk doit naître et mourir dans ce thread.
    try:
        root = tk.Tk()
        root.title("gazefocus - Réglages")
        root.resizable(False, False)
        root.attributes("-topmost", True)
        frame = ttk.Frame(root, padding=16)
        frame.grid()

        camera = tk.IntVar(value=current.camera)
        ttk.Label(frame, text="Caméra (0 = première)").grid(row=0, column=0, sticky="w", pady=4)
        ttk.Spinbox(frame, from_=0, to=9, width=6, textvariable=camera).grid(row=0, column=1)

        delays = {}
        for row, (name, label, low, high) in enumerate(DELAYS, 1):
            delays[name] = tk.DoubleVar(value=getattr(current, name))
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Spinbox(frame, from_=low, to=high, increment=0.1, width=6,
                        format="%.1f", textvariable=delays[name]).grid(row=row, column=1)

        options = {}
        for row, (name, label) in enumerate(OPTIONS, len(DELAYS) + 1):
            options[name] = tk.BooleanVar(value=getattr(current, name))
            ttk.Checkbutton(frame, text=label, variable=options[name]).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2)

        def save():
            try:
                new = Config(
                    camera=camera.get(),
                    **{name: max(0.0, var.get()) for name, var in delays.items()},
                    **{name: var.get() for name, var in options.items()},
                )
            except tk.TclError:
                return  # champ non numérique : on laisse la fenêtre ouverte
            config_module.save(new)
            on_save(new)
            root.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=len(DELAYS) + len(OPTIONS) + 1, column=0, columnspan=2,
                     sticky="e", pady=(12, 0))
        ttk.Button(buttons, text="Annuler", command=root.destroy).grid(row=0, column=0, padx=4)
        ttk.Button(buttons, text="Enregistrer", command=save).grid(row=0, column=1)
        root.mainloop()
    finally:
        _open.release()

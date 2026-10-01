"""Fenêtre de réglages (tkinter), ouverte depuis le menu de l'icône."""
import threading
import tkinter as tk
from tkinter import ttk

from . import config as config_module
from .config import Config
from .i18n import t

_open = threading.Lock()

DELAYS = (
    ("dwell", t("Temps de fixation avant bascule (s)", "Dwell time before switching (s)"), 0.1, 2.0),
    ("typing_cooldown", t("Garder le focus après une frappe (s)",
                          "Keep focus after a keystroke (s)"), 0.0, 15.0),
    ("mouse_cooldown", t("Garder le focus après la souris (s)",
                         "Keep focus after mouse use (s)"), 0.0, 10.0),
)
OPTIONS = (
    ("learn_from_clicks", t("Affiner la calibration à chaque clic",
                            "Refine the calibration with every click")),
    ("move_cursor", t("Amener le curseur sur la fenêtre choisie",
                      "Move the pointer to the focused window")),
    ("show_highlight", t("Entourer la fenêtre regardée (vert : active, orange : en attente)",
                         "Outline the window you look at (green: focused, orange: pending)")),
    ("use_eyes", t("Tenir compte des yeux, pas seulement de la tête (recalibrer après un changement)",
                   "Use the eyes, not only the head (recalibrate after changing this)")),
    ("same_screen", t("Basculer aussi entre fenêtres d'un même écran (expérimental)",
                      "Also switch between windows on the same screen (experimental)")),
)


def show(current: Config, on_save):
    """Ouvre la fenêtre dans son propre thread ; une seule à la fois."""
    if _open.acquire(blocking=False):
        threading.Thread(target=_run, args=(current, on_save), daemon=True).start()


def _run(current, on_save):
    # Tout objet Tk doit naître et mourir dans ce thread.
    try:
        root = tk.Tk()
        root.title(t("gazefocus - Réglages", "gazefocus - Settings"))
        root.resizable(False, False)
        root.attributes("-topmost", True)
        frame = ttk.Frame(root, padding=16)
        frame.grid()

        camera = tk.IntVar(value=current.camera)
        ttk.Label(frame, text=t("Caméra (0 = première)", "Camera (0 = first)")).grid(
            row=0, column=0, sticky="w", pady=4)
        ttk.Spinbox(frame, from_=0, to=9, width=6, textvariable=camera).grid(row=0, column=1)

        delays = {}
        for row, (name, label, low, high) in enumerate(DELAYS, 1):
            delays[name] = tk.DoubleVar(value=getattr(current, name))
            ttk.Label(frame, text=label).grid(row=row, column=0, sticky="w", pady=4)
            ttk.Spinbox(frame, from_=low, to=high, increment=0.1, width=6,
                        format="%.1f", textvariable=delays[name]).grid(row=row, column=1)

        options = {}
        row = len(DELAYS) + 1
        for name, label in OPTIONS:
            options[name] = tk.BooleanVar(value=getattr(current, name))
            ttk.Checkbutton(frame, text=label, variable=options[name]).grid(
                row=row, column=0, columnspan=2, sticky="w", pady=2)
            row += 1

        excluded = tk.StringVar(value=", ".join(current.excluded))
        ttk.Label(frame, text=t(
            "Applications où le focus ne bouge jamais (ex. vlc.exe, teams.exe)",
            "Apps where focus never moves on its own (e.g. vlc.exe, teams.exe)",
        )).grid(row=row, column=0, columnspan=2, sticky="w", pady=(10, 2))
        ttk.Entry(frame, textvariable=excluded).grid(row=row + 1, column=0, columnspan=2, sticky="ew")

        def save():
            try:
                new = Config(
                    camera=camera.get(),
                    excluded=config_module.parse_excluded(excluded.get()),
                    **{name: max(0.0, var.get()) for name, var in delays.items()},
                    **{name: var.get() for name, var in options.items()},
                )
            except tk.TclError:
                return  # champ non numérique : on laisse la fenêtre ouverte
            config_module.save(new)
            on_save(new)
            root.destroy()

        buttons = ttk.Frame(frame)
        buttons.grid(row=row + 2, column=0, columnspan=2, sticky="e", pady=(12, 0))
        ttk.Button(buttons, text=t("Annuler", "Cancel"), command=root.destroy).grid(
            row=0, column=0, padx=4)
        ttk.Button(buttons, text=t("Enregistrer", "Save"), command=save).grid(row=0, column=1)
        root.mainloop()
    finally:
        _open.release()

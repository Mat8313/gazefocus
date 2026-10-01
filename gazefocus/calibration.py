"""Écran de calibration : suivre du regard un point qui parcourt chaque écran."""
import math
import time

import cv2
import numpy as np
import win32gui

from .gaze import MIN_CALIBRATED
from .winfocus import focus_window

TITLE = "gazefocus - calibration"
# Le point longe les bords (ce sont eux qui fixent les frontières entre écrans)
# puis traverse le milieu.
PATH = ((0.5, 0.5), (0.06, 0.5), (0.06, 0.08), (0.94, 0.08), (0.94, 0.92),
        (0.06, 0.92), (0.06, 0.5), (0.94, 0.5), (0.5, 0.5))
DURATION = 14.0
# Le regard suit le point avec un léger retard : on associe chaque pose à la
# position que le point avait un instant plus tôt.
LATENCY = 0.15

_LENGTHS = [math.dist(a, b) for a, b in zip(PATH, PATH[1:])]


def path_point(progress: float):
    """Position sur le parcours pour une progression de 0 à 1, à vitesse constante."""
    remaining = min(max(progress, 0.0), 1.0) * sum(_LENGTHS)
    for (a, b), length in zip(zip(PATH, PATH[1:]), _LENGTHS):
        if remaining <= length:
            t = remaining / length
            return a[0] + (b[0] - a[0]) * t, a[1] + (b[1] - a[1]) * t
        remaining -= length
    return PATH[-1]


def _show_on(monitor):
    cv2.namedWindow(TITLE, cv2.WINDOW_NORMAL)
    cv2.setWindowProperty(TITLE, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
    cv2.moveWindow(TITLE, monitor.left, monitor.top)
    cv2.setWindowProperty(TITLE, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)
    cv2.waitKey(1)
    # Lancée depuis l'arrière-plan, la fenêtre n'aurait pas le clavier.
    hwnd = win32gui.FindWindow(None, TITLE)
    if hwnd:
        focus_window(hwnd)


def _draw(monitor, uv, lines):
    width, height = monitor.width, monitor.height
    canvas = np.zeros((height, width, 3), np.uint8)
    center = (int(uv[0] * width), int(uv[1] * height))
    cv2.circle(canvas, center, 18, (80, 220, 120), -1)
    cv2.circle(canvas, center, 4, (20, 20, 20), -1)
    for index, text in enumerate(lines):
        cv2.putText(canvas, text, (width // 2 - 430, height // 3 + 45 * index),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
    cv2.imshow(TITLE, canvas)
    return cv2.waitKey(1) & 0xFF


def _record_monitor(tracker, monitor, label, advice):
    """Renvoie les échantillons du parcours, ou None si annulé."""
    while True:  # attente du départ
        pose = tracker.read()
        status = "ESPACE pour commencer (Echap : annuler)" if pose else "Visage non detecte"
        key = _draw(monitor, PATH[0], (label, advice, status))
        if key == 27:
            return None
        if key == 32 and pose:
            break

    samples, start = [], time.monotonic()
    while (elapsed := time.monotonic() - start) < DURATION:
        pose = tracker.read()
        if pose:
            uv = path_point((elapsed - LATENCY) / DURATION)
            samples.append({"uv": list(uv), "raw": list(pose)})
        if _draw(monitor, path_point(elapsed / DURATION), ()) == 27:
            return None
    return samples


def run(tracker, monitors, model) -> bool:
    """Calibre tous les écrans. Le modèle n'est modifié que si tout est terminé."""
    advice = (
        "Suis le point des yeux, en bougeant la tete naturellement"
        if model.use_eyes else
        "Suis le point en tournant la tete vers lui"
    )
    results = {}
    try:
        for index, monitor in enumerate(monitors, 1):
            _show_on(monitor)
            label = f"Ecran {index}/{len(monitors)}"
            samples = _record_monitor(tracker, monitor, label, advice)
            if samples is None or len(samples) < MIN_CALIBRATED:
                return False
            results[monitor.name] = samples
    finally:
        cv2.destroyAllWindows()
        cv2.waitKey(1)
    for name, samples in results.items():
        model.set_calibration(name, samples)
    model.save()
    return True

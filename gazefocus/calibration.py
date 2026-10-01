"""Écran de calibration : suivre un point sur chaque écran."""
import statistics

import cv2
import numpy as np
import win32gui

from .winfocus import focus_window

TITLE = "gazefocus - calibration"
SAMPLES = 20
# Le centre, puis les quatre bords : ce sont les bords qui fixent les
# frontières entre écrans voisins.
POINTS = ((0.5, 0.5), (0.06, 0.5), (0.94, 0.5), (0.5, 0.08), (0.5, 0.92))


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


def _record_point(tracker, monitor, uv, label):
    """Renvoie la pose médiane en regardant le point, ou None si annulé."""
    width, height = monitor.width, monitor.height
    center = (int(uv[0] * width), int(uv[1] * height))
    samples, recording = [], False
    while len(samples) < SAMPLES:
        pose = tracker.read()
        canvas = np.zeros((height, width, 3), np.uint8)
        cv2.circle(canvas, center, 18, (80, 220, 120), -1)
        cv2.circle(canvas, center, 4, (20, 20, 20), -1)
        if pose is None:
            message, recording, samples = "Visage non detecte", False, []
        elif recording:
            samples.append(pose)
            message = "Ne bouge pas..."
        else:
            message = "Regarde le point puis appuie sur ESPACE (Echap : annuler)"
        for line, text in enumerate((label, message)):
            cv2.putText(canvas, text, (width // 2 - 420, height // 3 + 45 * line),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.9, (255, 255, 255), 2, cv2.LINE_AA)
        cv2.imshow(TITLE, canvas)
        key = cv2.waitKey(1) & 0xFF
        if key == 27:
            return None
        if key == 32 and pose is not None:
            recording = True
    return [statistics.median(axis) for axis in zip(*samples)]


def run(tracker, monitors, model) -> bool:
    """Calibre tous les écrans. Le modèle n'est modifié que si tout est terminé."""
    results = {}
    try:
        for screen, monitor in enumerate(monitors, 1):
            _show_on(monitor)
            samples = []
            for index, uv in enumerate(POINTS, 1):
                label = f"Ecran {screen}/{len(monitors)} - point {index}/{len(POINTS)}"
                raw = _record_point(tracker, monitor, uv, label)
                if raw is None:
                    return False
                samples.append({"uv": list(uv), "raw": raw})
            results[monitor.name] = samples
    finally:
        cv2.destroyAllWindows()
        cv2.waitKey(1)
    for name, samples in results.items():
        model.set_calibration(name, samples)
    model.save()
    return True

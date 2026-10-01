"""Calibration : associer une pose de tête à chaque écran, puis classer une pose."""
import json
import math
import statistics

import cv2
import numpy as np

from .tracker import DATA_DIR

CALIBRATION_PATH = DATA_DIR / "calibration.json"
SAMPLES = 30
# Au-delà de cette distance (en degrés) du centre le plus proche, on considère
# que tu ne regardes aucun écran (téléphone, plafond, fenêtre...).
MAX_DISTANCE = 30.0
# Le centre de l'écran actuel paraît 25 % plus proche : il faut tourner la tête
# un peu plus loin pour partir que pour revenir, ce qui évite le ping-pong.
STICKINESS = 0.75


def load() -> dict[str, tuple[float, float]]:
    if not CALIBRATION_PATH.exists():
        return {}
    data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    return {name: tuple(pose) for name, pose in data.items()}


def save(centers: dict[str, tuple[float, float]]):
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    CALIBRATION_PATH.write_text(json.dumps(centers, indent=2), encoding="utf-8")


def classify(pose, centers, current=None) -> str | None:
    """Nom de l'écran regardé, ou None si la pose est loin de tous les écrans."""
    best, best_score = None, math.inf
    for name, center in centers.items():
        distance = math.dist(pose, center)
        if distance > MAX_DISTANCE:
            continue
        score = distance * (STICKINESS if name == current else 1.0)
        if score < best_score:
            best, best_score = name, score
    return best


def run(tracker, monitors) -> dict[str, tuple[float, float]] | None:
    """Affiche un point au centre de chaque écran et enregistre la pose associée."""
    title = "gazefocus - calibration"
    centers = {}
    for monitor in monitors:
        width, height = monitor.right - monitor.left, monitor.bottom - monitor.top
        cv2.namedWindow(title, cv2.WINDOW_NORMAL)
        cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_NORMAL)
        cv2.moveWindow(title, monitor.left, monitor.top)
        cv2.setWindowProperty(title, cv2.WND_PROP_FULLSCREEN, cv2.WINDOW_FULLSCREEN)

        samples = []
        recording = False
        while len(samples) < SAMPLES:
            pose = tracker.read()
            canvas = np.zeros((height, width, 3), np.uint8)
            cv2.circle(canvas, (width // 2, height // 2), 18, (80, 220, 120), -1)
            if pose is None:
                message, recording, samples = "Visage non detecte", False, []
            elif recording:
                samples.append(pose)
                message = f"Ne bouge pas... {len(samples)}/{SAMPLES}"
            else:
                message = "Regarde le point puis appuie sur ESPACE (Echap : annuler)"
            cv2.putText(canvas, message, (40, 60), cv2.FONT_HERSHEY_SIMPLEX,
                        0.9, (255, 255, 255), 2, cv2.LINE_AA)
            cv2.imshow(title, canvas)
            key = cv2.waitKey(1) & 0xFF
            if key == 27:
                cv2.destroyAllWindows()
                return None
            if key == 32 and pose is not None:
                recording = True

        centers[monitor.name] = (
            statistics.median(p[0] for p in samples),
            statistics.median(p[1] for p in samples),
        )
    cv2.destroyAllWindows()
    save(centers)
    return centers

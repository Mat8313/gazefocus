"""Modèle du regard : de la pose mesurée à l'écran, puis au point regardé."""
import json
import math

import numpy as np

from .config import DATA_DIR

CALIBRATION_PATH = DATA_DIR / "calibration.json"
VERSION = 2
# Au-delà de cette distance (en degrés) de tout échantillon, on considère que tu
# ne regardes aucun écran (téléphone, plafond, fenêtre...).
MAX_DISTANCE = 30.0
# L'écran actuel paraît 25 % plus proche : il faut tourner la tête un peu plus
# loin pour partir que pour revenir, ce qui évite le ping-pong.
STICKINESS = 0.75
# Degrés de rotation du regard par unité de décalage d'iris (ordre de grandeur
# anatomique : l'iris se déplace d'environ 0,4 largeur d'œil pour 90°).
EYE_GAIN = 120.0
MAX_LEARNED = 40
MIN_CALIBRATED = 3


class GazeModel:
    """Échantillons par écran : {"uv": position sur l'écran (0..1), "raw": pose}."""

    def __init__(self, monitors=None, use_eyes=False):
        self.monitors = monitors or {}
        self.use_eyes = use_eyes
        self._fits = {}

    @classmethod
    def load(cls, use_eyes=False):
        try:
            data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return cls(use_eyes=use_eyes)
        if data.get("version") != VERSION:
            return cls(use_eyes=use_eyes)
        return cls(data["monitors"], use_eyes)

    def save(self):
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {"version": VERSION, "monitors": self.monitors}
        CALIBRATION_PATH.write_text(json.dumps(data), encoding="utf-8")

    def invalidate(self):
        self._fits = {}

    def set_calibration(self, name, samples):
        self.monitors[name] = {"calibrated": samples, "learned": []}
        self.invalidate()

    def covers(self, names) -> bool:
        return all(
            len(self.monitors.get(name, {}).get("calibrated", ())) >= MIN_CALIBRATED
            for name in names
        )

    def feature(self, raw):
        """Direction du regard (horizontale, verticale) en degrés."""
        yaw, pitch, eye = raw
        return (yaw + EYE_GAIN * eye if self.use_eyes else yaw, pitch)

    def _samples(self, name):
        entry = self.monitors[name]
        return entry["calibrated"] + entry["learned"]

    def distance(self, raw, name) -> float:
        feature = self.feature(raw)
        return min(math.dist(feature, self.feature(s["raw"])) for s in self._samples(name))

    def classify(self, raw, names, current=None):
        """Écran regardé parmi `names`, ou None si la pose est loin de tous."""
        best, best_score = None, math.inf
        for name in names:
            if name not in self.monitors:
                continue
            distance = self.distance(raw, name)
            if distance > MAX_DISTANCE:
                continue
            score = distance * (STICKINESS if name == current else 1.0)
            if score < best_score:
                best, best_score = name, score
        return best

    def learn(self, name, uv, raw, names) -> bool:
        """Ajoute un échantillon tiré d'un clic : on regarde là où on clique.

        Refusé si la pose désigne nettement un autre écran (clic à l'aveugle).
        """
        if name not in self.monitors:
            return False
        here = self.distance(raw, name)
        nearest = min(self.distance(raw, n) for n in names if n in self.monitors)
        if here > MAX_DISTANCE or here > max(1.5 * nearest, nearest + 5.0):
            return False
        learned = self.monitors[name]["learned"]
        learned.append({"uv": list(uv), "raw": list(raw)})
        del learned[:-MAX_LEARNED]
        self._fits.pop(name, None)
        return True

    def locate(self, raw, name):
        """Point regardé sur l'écran `name`, en coordonnées (u, v) de 0 à 1."""
        if name not in self._fits:
            samples = self._samples(name)
            features = np.array([[*self.feature(s["raw"]), 1.0] for s in samples])
            targets = np.array([s["uv"] for s in samples])
            if len(samples) < 3 or np.linalg.matrix_rank(features) < 3:
                self._fits[name] = None
            else:
                # Ajustement affine pose -> position, par moindres carrés.
                self._fits[name] = np.linalg.lstsq(features, targets, rcond=None)[0]
        fit = self._fits[name]
        if fit is None:
            return None
        u, v = np.array([*self.feature(raw), 1.0]) @ fit
        return float(u), float(v)

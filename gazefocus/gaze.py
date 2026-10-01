"""Modèle du regard : de la pose mesurée au point regardé, puis à l'écran."""
import json
import math

import numpy as np

from .config import DATA_DIR

CALIBRATION_PATH = DATA_DIR / "calibration.json"
VERSION = 3
MIN_CALIBRATED = 30
MAX_LEARNED = 200
# Un clic est une mesure exacte du point regardé : il pèse plus qu'un
# échantillon de calibration, et les clics récents plus que les anciens.
CLICK_WEIGHT = 2.0

# Pose : yaw, pitch, œil x, œil y, tête x, tête y, tête z.
HEAD, EYES, POSITION = (0, 1), (2, 3), (4, 5, 6)
# Mise à l'échelle pour que chaque axe varie d'environ 1 en usage normal.
SCALES = np.array([10.0, 10.0, 0.1, 0.1, 5.0, 5.0, 5.0])
# Pénalité de la régression : forte sur la position de la tête, qui bouge à
# peine pendant la calibration. Son effet ne s'apprend qu'avec beaucoup de clics.
RIDGE = np.array([1e-3, 1e-3, 1e-2, 1e-2, 30.0, 30.0, 30.0])

# Tête tournée à plus de 30° de tout ce qui a été vu : tu regardes ailleurs.
MAX_HEAD_DISTANCE = 30.0
# Point prédit à plus d'une demi-largeur hors de tout écran : aucun écran.
MAX_OUTSIDE = 0.5
# L'écran actuel est agrandi de 12 % : il faut regarder nettement chez le
# voisin pour basculer, ce qui évite le ping-pong sur la frontière.
STICKINESS = 0.12
# Un clic dont la position contredit la prédiction de plus d'un demi-écran est
# un clic à l'aveugle : on ne l'apprend pas.
MAX_CLICK_ERROR = 0.5


def _outside(uv) -> float:
    """Distance de (u, v) au carré [0, 1]², en fractions d'écran ; 0 dedans."""
    return math.hypot(*(max(-c, 0.0, c - 1.0) for c in uv))


class GazeModel:
    """Échantillons par écran : {"uv": position sur l'écran (0..1), "raw": pose}."""

    def __init__(self, monitors=None, use_eyes=True):
        self.monitors = monitors or {}
        self.use_eyes = use_eyes
        self._fits = {}

    @classmethod
    def load(cls, use_eyes=True):
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

    def _columns(self):
        return list(HEAD + (EYES if self.use_eyes else ()) + POSITION)

    def _fit(self, name):
        """Régression ridge pondérée pose -> (u, v), recalculée après chaque clic."""
        if name not in self._fits:
            entry = self.monitors[name]
            calibrated, learned = entry["calibrated"], entry["learned"]
            raws = np.array([s["raw"] for s in calibrated + learned])
            targets = np.array([s["uv"] for s in calibrated + learned])
            recency = 0.5 + 0.5 * np.arange(1, len(learned) + 1) / max(len(learned), 1)
            weights = np.concatenate([np.ones(len(calibrated)), CLICK_WEIGHT * recency])

            columns = self._columns()
            design = np.hstack([raws[:, columns] / SCALES[columns], np.ones((len(raws), 1))])
            weighted = design * weights[:, None]
            penalty = np.diag(np.append(RIDGE[columns], 0.0))  # pas de pénalité sur la constante
            coefficients = np.linalg.solve(design.T @ weighted + penalty, weighted.T @ targets)
            self._fits[name] = coefficients, raws[:, list(HEAD)]
        return self._fits[name]

    def locate(self, raw, name):
        """Point regardé sur l'écran `name`, en (u, v) ; hors de [0, 1] = à côté."""
        coefficients, _ = self._fit(name)
        columns = self._columns()
        features = np.append(np.asarray(raw)[columns] / SCALES[columns], 1.0)
        u, v = features @ coefficients
        return float(u), float(v)

    def _head_distance(self, raw, name) -> float:
        _, heads = self._fit(name)
        return float(np.min(np.linalg.norm(heads - np.asarray(raw)[list(HEAD)], axis=1)))

    def classify(self, raw, names, current=None):
        """Écran regardé parmi `names`, ou None si le regard est loin de tous."""
        best, best_score = None, math.inf
        for name in names:
            if name not in self.monitors:
                continue
            if self._head_distance(raw, name) > MAX_HEAD_DISTANCE:
                continue
            uv = self.locate(raw, name)
            outside = _outside(uv)
            if outside > MAX_OUTSIDE:
                continue
            score = max(outside - (STICKINESS if name == current else 0.0), 0.0)
            # À égalité (point dans deux écrans à la fois), le plus centré gagne.
            score += 1e-3 * math.dist(uv, (0.5, 0.5))
            if name == current:
                score -= 1e-3
            if score < best_score:
                best, best_score = name, score
        return best

    def learn(self, name, uv, raw) -> bool:
        """Ajoute un échantillon tiré d'un clic : on regarde là où on clique."""
        if name not in self.monitors:
            return False
        if math.dist(self.locate(raw, name), uv) > MAX_CLICK_ERROR:
            return False
        learned = self.monitors[name]["learned"]
        learned.append({"uv": list(uv), "raw": list(raw)})
        del learned[:-MAX_LEARNED]
        self._fits.pop(name, None)
        return True

"""Modèle du regard : de la pose mesurée au point regardé, puis à l'écran."""
import json
import math

import numpy as np

from .config import DATA_DIR

CALIBRATION_PATH = DATA_DIR / "calibration.json"
VERSION = 4
MIN_CALIBRATED = 30
MAX_LEARNED = 200
# Un clic est une mesure exacte du point regardé : il pèse plus qu'un
# échantillon de calibration, et les clics récents plus que les anciens.
CLICK_WEIGHT = 2.0

# Pose : yaw, pitch, œil x, œil y, tête x, tête y, tête z.
HEAD, EYES, SIDEWAYS, DEPTH = (0, 1), (2, 3), (4, 5), 6
# Mise à l'échelle pour que chaque variable varie d'environ 1 en usage normal.
SCALES = np.array([10.0, 10.0, 0.1, 0.1, 5.0, 5.0, 10.0])
# Pénalités de la régression ridge. Elles sont fortes là où la calibration
# apporte peu d'information : un effet ne s'apprend que si les données le montrent.
RIDGE_HEAD, RIDGE_EYES, RIDGE_POSITION, RIDGE_DISTANCE = 1e-3, 1e-2, 30.0, 1.0

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


def profile_key(monitors) -> str:
    """Identifie une disposition d'écrans : chacune a sa propre calibration."""
    return "|".join(sorted(
        f"{m.name}@{m.width}x{m.height}{m.left:+d}{m.top:+d}" for m in monitors
    ))


def _outside(uv) -> float:
    """Distance de (u, v) au carré [0, 1]², en fractions d'écran ; 0 dedans."""
    return math.hypot(*(max(-c, 0.0, c - 1.0) for c in uv))


def _read_profiles(profile="", names=()) -> dict:
    try:
        data = json.loads(CALIBRATION_PATH.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return {}
    if data.get("version") == VERSION:
        return data["profiles"]
    if data.get("version") == 3 and set(data["monitors"]) == set(names):
        # Ancien format, sans profils : la calibration devient celle de la
        # disposition actuelle si elle concerne bien ces écrans.
        return {profile: data["monitors"]}
    return {}


class GazeModel:
    """Échantillons par écran : {"uv": position sur l'écran (0..1), "raw": pose}."""

    def __init__(self, monitors=None, use_eyes=True, profile=""):
        self.monitors = monitors or {}
        self.use_eyes = use_eyes
        self.profile = profile
        self._fits = {}

    @classmethod
    def load(cls, use_eyes=True, profile="", names=()):
        return cls(_read_profiles(profile, names).get(profile), use_eyes, profile)

    def save(self):
        profiles = _read_profiles()
        profiles[self.profile] = self.monitors
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        data = {"version": VERSION, "profiles": profiles}
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

    def _design(self, raws, reference_depth):
        """Variables de la régression pour des poses (n, 7).

        Reculer rétrécit les écrans dans le champ de vision : un même angle
        correspond à un point plus éloigné. C'est un produit angle × distance,
        qu'un modèle linéaire ne peut apprendre que si on le lui fournit.
        """
        angular = list(HEAD + (EYES if self.use_eyes else ()))
        angles = raws[:, angular] / SCALES[angular]
        sideways = raws[:, list(SIDEWAYS)] / SCALES[list(SIDEWAYS)]
        depth = (raws[:, [DEPTH]] - reference_depth) / SCALES[DEPTH]
        design = np.hstack([angles, sideways, depth, angles * depth, np.ones((len(raws), 1))])
        penalty = np.concatenate([
            [RIDGE_HEAD] * 2, [RIDGE_EYES] * (len(angular) - 2),
            [RIDGE_POSITION] * 3, [RIDGE_DISTANCE] * len(angular),
            [0.0],  # pas de pénalité sur la constante
        ])
        return design, penalty

    def _fit(self, name):
        """Régression ridge pondérée pose -> (u, v), recalculée après chaque clic."""
        if name not in self._fits:
            entry = self.monitors[name]
            calibrated, learned = entry["calibrated"], entry["learned"]
            raws = np.array([s["raw"] for s in calibrated + learned])
            targets = np.array([s["uv"] for s in calibrated + learned])
            recency = 0.5 + 0.5 * np.arange(1, len(learned) + 1) / max(len(learned), 1)
            weights = np.concatenate([np.ones(len(calibrated)), CLICK_WEIGHT * recency])

            reference_depth = float(np.mean(raws[: len(calibrated), DEPTH]))
            design, penalty = self._design(raws, reference_depth)
            weighted = design * weights[:, None]
            coefficients = np.linalg.solve(
                design.T @ weighted + np.diag(penalty), weighted.T @ targets
            )
            self._fits[name] = coefficients, raws[:, list(HEAD)], reference_depth
        return self._fits[name]

    def locate(self, raw, name):
        """Point regardé sur l'écran `name`, en (u, v) ; hors de [0, 1] = à côté."""
        coefficients, _, reference_depth = self._fit(name)
        design, _ = self._design(np.asarray(raw, dtype=float)[None, :], reference_depth)
        u, v = (design @ coefficients)[0]
        return float(u), float(v)

    def _head_distance(self, raw, name) -> float:
        heads = self._fit(name)[1]
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

    def click_error(self, name, uv, raw):
        """Écart entre le point prédit et le clic, en fractions d'écran."""
        if name not in self.monitors:
            return None
        return math.dist(self.locate(raw, name), uv)

    def learn(self, name, uv, raw) -> bool:
        """Ajoute un échantillon tiré d'un clic : on regarde là où on clique."""
        error = self.click_error(name, uv, raw)
        if error is None or error > MAX_CLICK_ERROR:
            return False
        learned = self.monitors[name]["learned"]
        learned.append({"uv": list(uv), "raw": list(raw)})
        del learned[:-MAX_LEARNED]
        self._fits.pop(name, None)
        return True

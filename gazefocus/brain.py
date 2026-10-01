"""Logique du moteur, sans aucun appel à Windows : tout ce qui est ici se teste.

`engine.py` observe le monde (caméra, fenêtres, clavier), le décrit dans un
`World`, demande quoi faire à ces classes, puis applique le résultat.
"""
import statistics
from collections import deque
from dataclasses import dataclass

from .config import WINDOW_MIN_DWELL
from .decision import SwitchDecider

ACTIVE_INTERVAL = 1 / 20    # quand le regard bouge
RESTING_INTERVAL = 1 / 5    # quand il est posé : quatre fois moins de calcul
REST_AFTER = 2.0            # secondes sans mouvement avant de ralentir
# Mouvement minimal pour repasser en cadence rapide : degrés pour la tête,
# largeurs d'œil pour les iris. Au-dessus du tremblement résiduel du filtre.
MOTION_HEAD, MOTION_EYES = 1.5, 0.03
# Dérive : si l'erreur médiane des 20 derniers clics dépasse un quart d'écran,
# la calibration ne correspond plus à la position de l'utilisateur.
DRIFT_WINDOW, DRIFT_THRESHOLD = 20, 0.25


@dataclass
class World:
    """Ce que le moteur observe à un instant donné."""
    raw: tuple | None          # pose mesurée, None si aucun visage
    names: list                # écrans branchés
    foreground: int            # fenêtre qui a le focus (0 si aucune)
    current: str | None        # écran de cette fenêtre
    process: str               # exécutable de cette fenêtre, en minuscules
    now: float
    since_mouse: float
    since_key: float


@dataclass
class Outcome:
    focus: int | None          # fenêtre à qui donner le focus maintenant
    looked: int | None         # fenêtre regardée, pour le contour


class Brain:
    """Décide, image après image, quelle fenêtre est regardée et s'il faut basculer.

    top_window_on(écran) et window_at(écran, (u, v)) sont fournis par le moteur :
    ce sont les deux seules questions posées à Windows.
    """

    def __init__(self, config, model, top_window_on, window_at):
        self.config = config
        self.model = model
        self.top_window_on = top_window_on
        self.window_at = window_at
        self.screen_decider = SwitchDecider(config.switching())
        self.window_decider = SwitchDecider(config.switching(WINDOW_MIN_DWELL))

    def step(self, world: World) -> Outcome:
        config = self.config
        target = None
        if world.raw and world.process not in config.excluded:
            # Devant une app exclue (jeu, visio...), on ne touche à rien.
            target = self.model.classify(world.raw, world.names, world.current)

        other_screen = bool(target) and target != world.current
        if other_screen:
            looked = self.top_window_on(target)
        elif target and config.same_screen:
            looked = self.window_at(target, self.model.locate(world.raw, target))
        else:
            looked = world.foreground if target else None

        timing = (world.now, world.since_mouse, world.since_key)
        switch_to = self.screen_decider.update(target, world.current, *timing)
        candidate = looked if config.same_screen and not other_screen else None
        focus = self.window_decider.update(candidate, world.foreground, *timing)
        if switch_to:
            focus = looked
        return Outcome(focus or None, looked or None)


class DriftMonitor:
    """Signale quand les clics récents contredisent durablement la calibration."""

    def __init__(self, window=DRIFT_WINDOW, threshold=DRIFT_THRESHOLD):
        self.threshold = threshold
        self._errors = deque(maxlen=window)

    def add(self, error: float) -> bool:
        """Enregistre l'erreur d'un clic ; vrai s'il est temps d'avertir."""
        self._errors.append(error)
        full = len(self._errors) == self._errors.maxlen
        if full and statistics.median(self._errors) > self.threshold:
            self._errors.clear()  # prochain avertissement après une fenêtre complète
            return True
        return False

    def clear(self):
        self._errors.clear()


def moved(pose, reference) -> bool:
    if pose is None or reference is None:
        return pose is not reference
    return (
        max(abs(pose[i] - reference[i]) for i in (0, 1)) > MOTION_HEAD
        or max(abs(pose[i] - reference[i]) for i in (2, 3)) > MOTION_EYES
    )


class Pacer:
    """Cadence de traitement : rapide quand le regard bouge, lente quand il est posé."""

    def __init__(self):
        self._reference = None
        self._last_motion = None

    def interval(self, pose, now: float) -> float:
        if self._last_motion is None or moved(pose, self._reference):
            self._reference, self._last_motion = pose, now
        resting = now - self._last_motion > REST_AFTER
        return RESTING_INTERVAL if resting else ACTIVE_INTERVAL

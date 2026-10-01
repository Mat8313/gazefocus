"""Quand faut-il vraiment déplacer le focus ? C'est ici que ça se décide."""
from dataclasses import dataclass


@dataclass
class Settings:
    dwell: float = 0.3            # secondes à fixer un écran avant de basculer
    mouse_cooldown: float = 1.5   # la souris garde la main pendant ce délai
    typing_cooldown: float = 0.7  # on ne vole jamais le focus en pleine frappe


class SwitchDecider:
    def __init__(self, settings: Settings | None = None):
        self.settings = settings or Settings()
        self.candidate: str | None = None  # écran qu'on est en train de fixer
        self.candidate_since: float = 0.0  # depuis quand (horloge `now`)

    def update(self, target, current, now, since_mouse, since_key) -> str | None:
        """Appelée à chaque image. Renvoie l'écran vers lequel basculer, ou None.

        target      : écran regardé d'après la caméra (None = aucun écran)
        current     : écran de la fenêtre qui a le focus en ce moment
        now         : horloge monotone, en secondes
        since_mouse : secondes écoulées depuis la dernière activité souris
        since_key   : secondes écoulées depuis la dernière frappe clavier
        """
        if target is None or target == current:
            self.candidate = None
            return None
        if target != self.candidate:
            self.candidate, self.candidate_since = target, now
        if now - self.candidate_since < self.settings.dwell:
            return None
        # Le chrono continue pendant la frappe : la bascule part dès que tu
        # t'arrêtes, si tu regardes toujours l'autre écran.
        if since_mouse < self.settings.mouse_cooldown:
            return None
        if since_key < self.settings.typing_cooldown:
            return None
        self.candidate = None
        return target

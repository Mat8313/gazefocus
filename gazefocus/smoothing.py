"""Filtre « One Euro » : lisse fort au repos, réagit vite en mouvement."""
import math

import numpy as np


def _alpha(cutoff, dt):
    r = 2 * math.pi * cutoff * dt
    return r / (r + 1)


class OneEuroFilter:
    """Filtre passe-bas dont la fréquence de coupure monte avec la vitesse.

    min_cutoff : coupure au repos (Hz). Plus bas = moins de tremblement.
    beta       : gain de la coupure par unité de vitesse. Plus haut = moins de
                 retard en mouvement. Peut être un vecteur, une valeur par axe.
    """

    def __init__(self, min_cutoff=1.0, beta=0.0, derivative_cutoff=1.0):
        self.min_cutoff = min_cutoff
        self.beta = np.asarray(beta, dtype=float)
        self.derivative_cutoff = derivative_cutoff
        self.reset()

    def reset(self):
        self._value = self._speed = self._time = None

    def __call__(self, value, now):
        value = np.asarray(value, dtype=float)
        if self._value is None:
            self._value, self._speed, self._time = value, np.zeros_like(value), now
            return value
        dt = max(now - self._time, 1e-3)
        a = _alpha(self.derivative_cutoff, dt)
        self._speed = a * (value - self._value) / dt + (1 - a) * self._speed
        a = _alpha(self.min_cutoff + self.beta * np.abs(self._speed), dt)
        self._value = a * value + (1 - a) * self._value
        self._time = now
        return self._value

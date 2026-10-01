import numpy as np

from gazefocus.smoothing import OneEuroFilter

FPS = 15


def run(signal, **options):
    smooth = OneEuroFilter(**options)
    return np.array([smooth([x], i / FPS)[0] for i, x in enumerate(signal)])


def test_reduit_le_tremblement_au_repos():
    noise = np.random.default_rng(0).normal(0, 0.3, 300)
    assert run(noise, min_cutoff=1.0, beta=0.05).std() < noise.std() / 1.5


def test_suit_un_mouvement_rapide_sans_trainer():
    # Rotation de 30° en un tiers de seconde, puis immobile.
    step = np.concatenate([np.zeros(15), np.linspace(0, 30, 5), np.full(10, 30.0)])
    fixed = run(step, min_cutoff=1.0, beta=0.0)
    adaptive = run(step, min_cutoff=1.0, beta=0.05)
    assert abs(adaptive[22] - 30) < abs(fixed[22] - 30) / 2
    assert abs(adaptive[22] - 30) < 3.0

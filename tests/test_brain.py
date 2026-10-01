"""Le moteur est testé à travers `Brain`, avec un faux modèle et de fausses fenêtres."""
from gazefocus.brain import (ACTIVE_INTERVAL, DRIFT_WINDOW, RESTING_INTERVAL, Brain,
                             DriftMonitor, Pacer, World)
from gazefocus.config import Config

A, B = "ecran-A", "ecran-B"
TERMINAL, NOTES, BROWSER = 101, 202, 203  # fenêtres : terminal sur A, notes et navigateur sur B
POSE = (0.0, 0.0, 0.0, 0.0, 0.0, 0.0, -60.0)
IDLE = 60.0


class FakeModel:
    """Le « regard » est décidé par le test, pas par une caméra."""

    def __init__(self):
        self.looking_at = A
        self.point = (0.5, 0.5)

    def classify(self, raw, names, current=None):
        return self.looking_at if self.looking_at in names else None

    def locate(self, raw, name):
        return self.point


def make(config=None):
    model = FakeModel()
    top = {A: TERMINAL, B: NOTES}
    # Sur l'écran B, la moitié gauche est aux notes, la droite au navigateur.
    at = lambda name, uv: (NOTES if uv[0] < 0.5 else BROWSER) if name == B else TERMINAL
    return Brain(config or Config(), model, top.get, at), model


def run(brain, duration, start=0.0, foreground=TERMINAL, current=A, process="code.exe",
        raw=POSE, since_mouse=IDLE, since_key=IDLE):
    """Simule `duration` secondes à 20 images/s ; renvoie tous les résultats."""
    outcomes, t = [], start
    while t <= start + duration:
        outcomes.append(brain.step(World(raw, [A, B], foreground, current, process,
                                         t, since_mouse, since_key)))
        t += 0.05
    return outcomes


def focused(outcomes):
    return [o.focus for o in outcomes if o.focus]


def test_regarder_l_autre_ecran_donne_le_focus_a_sa_fenetre():
    brain, model = make()
    model.looking_at = B
    outcomes = run(brain, 1.0)
    assert set(focused(outcomes)) == {NOTES}
    assert outcomes[0].looked == NOTES and outcomes[0].focus is None  # d'abord « en attente »


def test_regarder_l_ecran_actuel_ne_fait_rien():
    brain, _ = make()
    outcomes = run(brain, 1.0)
    assert focused(outcomes) == []
    assert outcomes[-1].looked == TERMINAL


def test_pas_de_visage_pas_de_contour():
    brain, model = make()
    model.looking_at = B
    outcomes = run(brain, 1.0, raw=None)
    assert focused(outcomes) == [] and outcomes[-1].looked is None


def test_application_exclue_au_premier_plan():
    brain, model = make(Config(excluded=["jeu.exe"]))
    model.looking_at = B
    outcomes = run(brain, 1.0, process="jeu.exe")
    assert focused(outcomes) == [] and outcomes[-1].looked is None
    assert set(focused(run(brain, 1.0, start=2.0, process="code.exe"))) == {NOTES}


def test_frappe_et_souris_retiennent_le_focus():
    brain, model = make()
    model.looking_at = B
    assert focused(run(brain, 1.0, since_key=0.5)) == []
    assert focused(run(brain, 1.0, start=2.0, since_mouse=0.5)) == []


def test_ecran_debranche():
    brain, model = make()
    model.looking_at = "ecran-C"
    assert focused(run(brain, 1.0)) == []


def test_fenetres_d_un_meme_ecran_seulement_si_active():
    brain, model = make()
    model.looking_at, model.point = B, (0.8, 0.5)
    assert focused(run(brain, 1.5, foreground=NOTES, current=B)) == []

    brain, model = make(Config(same_screen=True))
    model.looking_at, model.point = B, (0.8, 0.5)
    outcomes = run(brain, 1.5, foreground=NOTES, current=B)
    assert set(focused(outcomes)) == {BROWSER}
    # Plus lent qu'entre deux écrans : au moins 0,6 s de regard posé.
    assert all(o.focus is None for o in outcomes[:12])


def test_derive_signalee_apres_une_fenetre_de_mauvais_clics():
    drift = DriftMonitor()
    assert not any(drift.add(0.4) for _ in range(DRIFT_WINDOW - 1))
    assert drift.add(0.4)
    # Remise à zéro : pas de nouvel avertissement avant une fenêtre complète.
    assert not any(drift.add(0.4) for _ in range(DRIFT_WINDOW - 1))


def test_pas_de_derive_si_les_clics_sont_justes():
    drift = DriftMonitor()
    assert not any(drift.add(0.05) for _ in range(100))
    # Quelques clics à l'aveugle ne suffisent pas : c'est la médiane qui compte.
    assert not any(drift.add(0.9 if i % 4 == 0 else 0.05) for i in range(100))


def test_cadence_lente_au_repos_rapide_des_que_ca_bouge():
    pacer = Pacer()
    assert pacer.interval(POSE, 0.0) == ACTIVE_INTERVAL
    assert pacer.interval(POSE, 1.0) == ACTIVE_INTERVAL
    assert pacer.interval(POSE, 2.5) == RESTING_INTERVAL
    turned = (5.0,) + POSE[1:]
    assert pacer.interval(turned, 2.7) == ACTIVE_INTERVAL
    assert pacer.interval(None, 6.0) == ACTIVE_INTERVAL      # le visage disparaît
    assert pacer.interval(None, 9.0) == RESTING_INTERVAL     # et reste absent

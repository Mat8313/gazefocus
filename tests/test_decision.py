from gazefocus.decision import Settings, SwitchDecider

A, B = "ecran-A", "ecran-B"
IDLE = 60.0


def feed(decider, target, start, duration, current=A, since_mouse=IDLE, since_key=IDLE):
    """Simule `duration` secondes à 15 images/s et renvoie les bascules demandées."""
    results, t = [], start
    while t <= start + duration:
        results.append(decider.update(target, current, t, since_mouse, since_key))
        t += 1 / 15
    return [r for r in results if r]


def test_regard_soutenu_bascule():
    assert B in feed(SwitchDecider(Settings()), B, 0.0, 1.0)


def test_coup_d_oeil_rapide_ignore():
    decider = SwitchDecider(Settings(dwell=0.3))
    assert feed(decider, B, 0.0, 0.15) == []
    assert feed(decider, A, 0.2, 1.0) == []


def test_rien_a_faire_si_on_regarde_l_ecran_actif():
    assert feed(SwitchDecider(Settings()), A, 0.0, 1.0) == []


def test_aucun_ecran_regarde():
    assert feed(SwitchDecider(Settings()), None, 0.0, 1.0) == []


def test_la_souris_garde_la_main():
    assert feed(SwitchDecider(Settings()), B, 0.0, 1.0, since_mouse=0.2) == []


def test_pas_de_vol_de_focus_en_pleine_frappe():
    assert feed(SwitchDecider(Settings()), B, 0.0, 1.0, since_key=0.1) == []

"""Le modèle est testé sur un utilisateur simulé, avec du bruit de mesure."""
import numpy as np
import pytest

from gazefocus.calibration import path_point
from gazefocus.gaze import GazeModel

LEFT, RIGHT = "gauche", "droite"
NAMES = [LEFT, RIGHT]
# Centre de chaque écran en degrés (yaw, pitch) vu de l'utilisateur. L'écran de
# gauche est vers les yaw positifs, comme sur une vraie webcam.
CENTERS = {LEFT: (12.0, 0.0), RIGHT: (-12.0, -3.0)}
HALF = (12.0, 8.0)
# Degrés de rotation de l'œil par unité de décalage d'iris : inconnus du modèle.
EYE_GAIN = (140.0, 100.0)


class Person:
    """Regarde un point en partageant la rotation entre la tête et les yeux."""

    def __init__(self, seed, head_position=(0.0, 0.0, 50.0)):
        self.rng = np.random.default_rng(seed)
        self.head_position = head_position

    def pose(self, name, uv):
        gaze = [CENTERS[name][i] + (uv[i] - 0.5) * 2 * HALF[i] for i in range(2)]
        share = self.rng.uniform(0.3, 0.8)  # part de la rotation prise par la tête
        head = [g * share + self.rng.normal(0, 0.3) for g in gaze]
        eyes = [(g - h) / k + self.rng.normal(0, 0.004)
                for g, h, k in zip(gaze, head, EYE_GAIN)]
        position = [p + self.rng.normal(0, 0.3) for p in self.head_position]
        return (*head, *eyes, *position)


def calibrate(person, use_eyes=True, samples=180):
    model = GazeModel(use_eyes=use_eyes)
    for name in NAMES:
        points = [path_point(i / (samples - 1)) for i in range(samples)]
        model.set_calibration(
            name, [{"uv": list(uv), "raw": list(person.pose(name, uv))} for uv in points]
        )
    return model


@pytest.fixture(scope="module")
def person():
    return Person(seed=1)


@pytest.fixture
def model(person):
    return calibrate(person)


def test_parcours_de_calibration():
    assert path_point(0.0) == (0.5, 0.5)
    assert path_point(1.0) == pytest.approx((0.5, 0.5))
    points = [path_point(i / 200) for i in range(201)]
    assert min(p[0] for p in points) == pytest.approx(0.06)
    assert max(p[1] for p in points) == pytest.approx(0.92)


def test_classe_le_bon_ecran(model, person):
    rng = np.random.default_rng(2)
    hits = total = 0
    for name in NAMES:
        for _ in range(300):
            uv = rng.uniform(0.1, 0.9, size=2)
            hits += model.classify(person.pose(name, uv), NAMES) == name
            total += 1
    assert hits / total > 0.97


def test_localise_le_point_regarde(model, person):
    rng = np.random.default_rng(3)
    errors = []
    for _ in range(300):
        uv = rng.uniform(0.0, 1.0, size=2)
        errors.append(np.linalg.norm(np.subtract(model.locate(person.pose(LEFT, uv), LEFT), uv)))
    assert np.mean(errors) < 0.06


def test_les_yeux_ameliorent_la_precision(person):
    rng = np.random.default_rng(4)
    with_eyes, head_only = calibrate(person), calibrate(person, use_eyes=False)
    points = [rng.uniform(0.0, 1.0, size=2) for _ in range(300)]
    poses = [person.pose(LEFT, uv) for uv in points]

    def error(m):
        return np.mean([np.linalg.norm(np.subtract(m.locate(p, LEFT), uv))
                        for p, uv in zip(poses, points)])

    assert error(with_eyes) < error(head_only) / 2


def test_regard_ailleurs_rejete(model, person):
    far = list(person.pose(LEFT, (0.5, 0.5)))
    far[1] += 60.0  # tête levée vers le plafond
    assert model.classify(far, NAMES) is None


def test_l_ecran_actuel_retient_pres_de_la_frontiere(model):
    quiet = Person(seed=5)
    # Juste de l'autre côté du bord commun : pas assez pour quitter l'écran actuel.
    # (Dans cette simulation, le bord commun est à u = 1 pour l'écran de droite.)
    pose = quiet.pose(RIGHT, (0.95, 0.5))
    assert model.classify(pose, NAMES, current=LEFT) == LEFT
    pose = quiet.pose(RIGHT, (0.65, 0.5))
    assert model.classify(pose, NAMES, current=LEFT) == RIGHT


def test_ecran_debranche_ignore(model, person):
    assert model.classify(person.pose(RIGHT, (0.8, 0.5)), [LEFT]) in (LEFT, None)


def test_couverture(model):
    assert model.covers(NAMES)
    assert not model.covers([LEFT, "nouvel-ecran"])


def test_apprend_d_un_clic_coherent(model, person):
    assert model.learn(LEFT, (0.2, 0.7), person.pose(LEFT, (0.2, 0.7)))
    assert len(model.monitors[LEFT]["learned"]) == 1


def test_refuse_un_clic_a_l_aveugle(model, person):
    # Clic sur l'écran de gauche en regardant le milieu de celui de droite.
    assert not model.learn(LEFT, (0.5, 0.5), person.pose(RIGHT, (0.5, 0.5)))


def test_les_clics_corrigent_un_changement_de_posture(model):
    # L'utilisateur s'est décalé : toutes ses poses sont déplacées de 4°.
    moved = Person(seed=6)
    rng = np.random.default_rng(7)

    def shifted(uv):
        pose = list(moved.pose(LEFT, uv))
        pose[0] += 4.0
        return pose

    points = [rng.uniform(0.0, 1.0, size=2) for _ in range(150)]

    def error():
        return np.mean([np.linalg.norm(np.subtract(model.locate(shifted(uv), LEFT), uv))
                        for uv in points])

    before = error()
    for _ in range(150):
        uv = rng.uniform(0.0, 1.0, size=2)
        model.learn(LEFT, uv, shifted(uv))
    assert error() < before * 0.7

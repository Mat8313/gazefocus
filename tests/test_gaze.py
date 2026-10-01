import pytest

from gazefocus.gaze import GazeModel

LEFT, RIGHT = "gauche", "droite"
POINTS = ((0.5, 0.5), (0.06, 0.5), (0.94, 0.5), (0.5, 0.08), (0.5, 0.92))


def calibrated(center_yaw, half_width=12.0, half_height=8.0):
    """Écran dont le centre est à `center_yaw` degrés, vu sans erreur de mesure."""
    return {
        "calibrated": [
            {"uv": [u, v], "raw": [center_yaw + (u - 0.5) * 2 * half_width,
                                   (v - 0.5) * 2 * half_height, 0.0]}
            for u, v in POINTS
        ],
        "learned": [],
    }


@pytest.fixture
def model():
    # L'écran de gauche est vers les yaw positifs, comme sur une vraie webcam.
    return GazeModel({LEFT: calibrated(12.0), RIGHT: calibrated(-12.0)})


def test_classe_chaque_cote(model):
    names = [LEFT, RIGHT]
    assert model.classify((10.0, 0.0, 0.0), names) == LEFT
    assert model.classify((-10.0, 0.0, 0.0), names) == RIGHT


def test_pose_lointaine_rejetee(model):
    assert model.classify((0.0, 70.0, 0.0), [LEFT, RIGHT]) is None


def test_l_ecran_actuel_retient_pres_de_la_frontiere(model):
    names, pose = [LEFT, RIGHT], (-0.1, 0.0, 0.0)
    assert model.classify(pose, names) == RIGHT
    assert model.classify(pose, names, current=LEFT) == LEFT


def test_ecran_debranche_ignore(model):
    assert model.classify((-10.0, 0.0, 0.0), [LEFT]) == LEFT


def test_couverture(model):
    assert model.covers([LEFT, RIGHT])
    assert not model.covers([LEFT, "nouvel-ecran"])


def test_localise_le_point_regarde(model):
    u, v = model.locate((12.0 + 6.0, -4.0, 0.0), LEFT)
    assert u == pytest.approx(0.75, abs=0.02)
    assert v == pytest.approx(0.25, abs=0.02)


def test_apprend_d_un_clic_coherent(model):
    names = [LEFT, RIGHT]
    assert model.learn(LEFT, (0.1, 0.5), (1.0, 0.0, 0.0), names)
    assert len(model.monitors[LEFT]["learned"]) == 1


def test_refuse_un_clic_a_l_aveugle(model):
    # La tête pointe franchement à droite pendant un clic sur l'écran de gauche.
    assert not model.learn(LEFT, (0.5, 0.5), (-15.0, 0.0, 0.0), [LEFT, RIGHT])


def test_les_yeux_decalent_le_regard():
    model = GazeModel({LEFT: calibrated(12.0), RIGHT: calibrated(-12.0)}, use_eyes=True)
    # Tête droit devant, yeux tournés : le décalage d'iris fait pencher la balance.
    assert model.classify((0.0, 0.0, 0.08), [LEFT, RIGHT]) == LEFT
    assert model.classify((0.0, 0.0, -0.08), [LEFT, RIGHT]) == RIGHT

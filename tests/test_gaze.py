"""Le modèle est testé sur un utilisateur simulé, avec géométrie et bruit de mesure."""
import json
import math
from types import SimpleNamespace

import numpy as np
import pytest

from gazefocus import gaze
from gazefocus.calibration import path_point
from gazefocus.gaze import GazeModel, profile_key

LEFT, RIGHT = "gauche", "droite"
NAMES = [LEFT, RIGHT]
# Écrans posés côte à côte sur un plan face à l'utilisateur, en cm :
# (bord gauche x, bord haut y, largeur, hauteur). x positif = yaw positif.
SCREENS = {LEFT: (0.0, -9.0, 30.0, 18.0), RIGHT: (-30.0, -11.0, 30.0, 18.0)}
# Degrés de rotation de l'œil par unité de décalage d'iris : inconnus du modèle.
EYE_GAIN = (140.0, 100.0)
NORMAL, FAR = 60.0, 85.0


class Person:
    """Regarde un point en partageant la rotation entre la tête et les yeux."""

    def __init__(self, seed, distance=NORMAL, sideways=0.0):
        self.rng = np.random.default_rng(seed)
        self.distance, self.sideways = distance, sideways

    def pose(self, name, uv):
        x0, y0, width, height = SCREENS[name]
        point = (x0 + uv[0] * width, y0 + uv[1] * height)
        head_at = (self.sideways, 0.0)
        gaze_angles = [math.degrees(math.atan2(p - h, self.distance))
                       for p, h in zip(point, head_at)]
        share = self.rng.uniform(0.3, 0.8)  # part de la rotation prise par la tête
        head = [g * share + self.rng.normal(0, 0.3) for g in gaze_angles]
        eyes = [(g - h) / k + self.rng.normal(0, 0.004)
                for g, h, k in zip(gaze_angles, head, EYE_GAIN)]
        position = [self.sideways, 0.0, -self.distance] + self.rng.normal(0, 0.3, 3)
        return (*head, *eyes, *position)


def calibrate(distances=(NORMAL,), use_eyes=True, samples=180, seed=1):
    model = GazeModel(use_eyes=use_eyes)
    for name in NAMES:
        collected = []
        for index, distance in enumerate(distances):
            person = Person(seed + index, distance)
            for i in range(samples):
                uv = path_point(i / (samples - 1))
                collected.append({"uv": list(uv), "raw": list(person.pose(name, uv))})
        model.set_calibration(name, collected)
    return model


def mean_error(model, person, name=LEFT, seed=3, count=300):
    rng = np.random.default_rng(seed)
    points = [rng.uniform(0.0, 1.0, size=2) for _ in range(count)]
    return float(np.mean([
        np.linalg.norm(np.subtract(model.locate(person.pose(name, uv), name), uv))
        for uv in points
    ]))


@pytest.fixture
def model():
    return calibrate()


def test_parcours_de_calibration():
    assert path_point(0.0) == (0.5, 0.5)
    assert path_point(1.0) == pytest.approx((0.5, 0.5))
    points = [path_point(i / 200) for i in range(201)]
    assert min(p[0] for p in points) == pytest.approx(0.06)
    assert max(p[1] for p in points) == pytest.approx(0.92)


def test_classe_le_bon_ecran(model):
    person, rng = Person(seed=10), np.random.default_rng(2)
    hits = total = 0
    for name in NAMES:
        for _ in range(300):
            uv = rng.uniform(0.1, 0.9, size=2)
            hits += model.classify(person.pose(name, uv), NAMES) == name
            total += 1
    assert hits / total > 0.97


def test_localise_le_point_regarde(model):
    assert mean_error(model, Person(seed=11)) < 0.06


def test_les_yeux_ameliorent_la_precision(model):
    head_only = calibrate(use_eyes=False)
    assert mean_error(model, Person(seed=12)) < mean_error(head_only, Person(seed=12)) / 2


def test_regard_ailleurs_rejete(model):
    far = list(Person(seed=13).pose(LEFT, (0.5, 0.5)))
    far[1] += 60.0  # tête levée vers le plafond
    assert model.classify(far, NAMES) is None


def test_l_ecran_actuel_retient_pres_de_la_frontiere(model):
    person = Person(seed=5)
    # Le bord commun est à u = 1 pour l'écran de droite. Juste de l'autre côté,
    # on ne quitte pas l'écran actuel ; franchement plus loin, si.
    assert model.classify(person.pose(RIGHT, (0.95, 0.5)), NAMES, current=LEFT) == LEFT
    assert model.classify(person.pose(RIGHT, (0.65, 0.5)), NAMES, current=LEFT) == RIGHT


def test_ecran_debranche_ignore(model):
    assert model.classify(Person(seed=14).pose(RIGHT, (0.2, 0.5)), [LEFT]) in (LEFT, None)


def test_couverture(model):
    assert model.covers(NAMES)
    assert not model.covers([LEFT, "nouvel-ecran"])


def test_apprend_d_un_clic_coherent(model):
    assert model.learn(LEFT, (0.2, 0.7), Person(seed=15).pose(LEFT, (0.2, 0.7)))
    assert len(model.monitors[LEFT]["learned"]) == 1


def test_refuse_un_clic_a_l_aveugle(model):
    # Clic sur l'écran de gauche en regardant le milieu de celui de droite.
    blind = Person(seed=16).pose(RIGHT, (0.5, 0.5))
    assert model.click_error(LEFT, (0.5, 0.5), blind) > 0.5
    assert not model.learn(LEFT, (0.5, 0.5), blind)


def test_reculer_sans_l_avoir_appris_degrade(model):
    assert mean_error(model, Person(seed=20, distance=FAR)) > 2 * mean_error(model, Person(seed=20))


def test_calibration_en_deux_distances_compense_le_recul():
    one, two = calibrate((NORMAL,)), calibrate((NORMAL, FAR))
    for distance in (72.0, FAR, 95.0):  # entre les deux, à la seconde, au-delà
        person = lambda: Person(seed=21, distance=distance)
        assert mean_error(two, person()) < 0.08
        assert mean_error(two, person()) < mean_error(one, person()) / 2
    # Et la précision à la distance normale n'en souffre pas.
    assert mean_error(two, Person(seed=22)) < 0.06


def test_les_clics_corrigent_un_decalage_lateral(model):
    # L'utilisateur s'est décalé de 12 cm sur le côté depuis la calibration.
    moved, rng = Person(seed=6, sideways=12.0), np.random.default_rng(7)
    before = mean_error(model, Person(seed=8, sideways=12.0))
    for _ in range(150):
        uv = rng.uniform(0.0, 1.0, size=2)
        model.learn(LEFT, uv, moved.pose(LEFT, uv))
    assert mean_error(model, Person(seed=8, sideways=12.0)) < before * 0.6


def monitor(name, left=0, width=1920, height=1080):
    return SimpleNamespace(name=name, left=left, top=0, width=width, height=height)


def test_un_profil_par_disposition(tmp_path, monkeypatch, model):
    monkeypatch.setattr(gaze, "CALIBRATION_PATH", tmp_path / "calibration.json")
    monkeypatch.setattr(gaze, "DATA_DIR", tmp_path)
    docked = profile_key([monitor(LEFT), monitor(RIGHT, left=1920)])
    alone = profile_key([monitor(LEFT)])
    assert docked != alone
    assert docked == profile_key([monitor(RIGHT, left=1920), monitor(LEFT)])

    model.profile = docked
    model.save()
    assert GazeModel.load(profile=docked).covers(NAMES)
    assert not GazeModel.load(profile=alone).covers([LEFT])

    # Enregistrer un second profil ne doit pas effacer le premier.
    other = GazeModel({LEFT: model.monitors[LEFT]}, profile=alone)
    other.save()
    assert GazeModel.load(profile=docked).covers(NAMES)
    assert GazeModel.load(profile=alone).covers([LEFT])


def test_reprend_une_calibration_de_l_ancien_format(tmp_path, monkeypatch, model):
    path = tmp_path / "calibration.json"
    monkeypatch.setattr(gaze, "CALIBRATION_PATH", path)
    path.write_text(json.dumps({"version": 3, "monitors": model.monitors}), encoding="utf-8")
    assert GazeModel.load(profile="p", names=NAMES).covers(NAMES)
    assert not GazeModel.load(profile="p", names=[LEFT, "autre"]).covers([LEFT])

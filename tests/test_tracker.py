from gazefocus.tracker import nearest_face


def matrix(distance_cm):
    """Matrice de transformation d'un visage à cette distance de la caméra."""
    return [[1, 0, 0, 0], [0, 1, 0, 0], [0, 0, 1, -distance_cm], [0, 0, 0, 1]]


def test_un_seul_visage():
    assert nearest_face([matrix(60)]) == 0


def test_le_visage_le_plus_proche_est_suivi():
    # Quelqu'un passe derrière (150 cm), détecté avant l'utilisateur (55 cm).
    assert nearest_face([matrix(150), matrix(55), matrix(200)]) == 1

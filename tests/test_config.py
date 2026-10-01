from dataclasses import asdict

from gazefocus.config import Config, parse_excluded


def test_liste_d_exclusion():
    assert parse_excluded("VLC, teams.exe ; vlc.exe,, ") == ["vlc.exe", "teams.exe"]
    assert parse_excluded("") == []


def test_valeurs_par_defaut_independantes():
    first, second = Config(), Config()
    first.excluded.append("jeu.exe")
    assert second.excluded == []


def test_reglages_de_bascule():
    settings = Config(dwell=0.3).switching(min_dwell=0.6)
    assert settings.dwell == 0.6
    assert Config(**asdict(Config(camera=2))).camera == 2

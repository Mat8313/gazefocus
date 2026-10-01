"""Langue de l'interface : français si Windows est en français, anglais sinon."""
import ctypes

LANG_FRENCH = 0x0C


def _windows_is_french() -> bool:
    try:
        # Les 10 bits de poids faible identifient la langue, sans la région.
        return ctypes.windll.kernel32.GetUserDefaultUILanguage() & 0x3FF == LANG_FRENCH
    except (AttributeError, OSError):
        return False


FRENCH = _windows_is_french()


def t(french: str, english: str) -> str:
    """Les deux versions sont écrites côte à côte, là où le texte est utilisé."""
    return french if FRENCH else english

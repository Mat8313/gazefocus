"""Icône de la zone de notification et son menu."""
import pystray
from PIL import Image, ImageDraw

from . import autostart, engine as eng

COLORS = {
    eng.ACTIVE: (80, 220, 120),
    eng.PAUSED: (150, 150, 150),
    eng.CALIBRATING: (90, 160, 255),
    eng.NEEDS_CALIBRATION: (255, 180, 60),
    eng.ERROR: (235, 80, 80),
}
LABELS = {
    eng.ACTIVE: "actif",
    eng.PAUSED: "en pause",
    eng.CALIBRATING: "calibration en cours",
    eng.NEEDS_CALIBRATION: "calibration nécessaire",
    eng.ERROR: "erreur",
}


def _icon_image(state) -> Image.Image:
    """Un œil stylisé dont l'iris prend la couleur de l'état."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 14, 62, 50), fill=(245, 245, 245), outline=(40, 40, 40), width=3)
    draw.ellipse((20, 20, 44, 44), fill=COLORS[state])
    draw.ellipse((27, 27, 37, 37), fill=(20, 20, 20))
    return image


def run(camera=0, settings=None):
    def on_state(state, detail=""):
        icon.icon = _icon_image(state)
        icon.title = f"gazefocus : {LABELS[state]}"
        icon.update_menu()
        if state == eng.ERROR:
            icon.notify(detail or "Erreur inconnue", "gazefocus")
        elif state == eng.NEEDS_CALIBRATION:
            icon.notify("Calibration annulée. Relance-la depuis le menu.", "gazefocus")

    engine = eng.Engine(camera, settings, on_state)

    def toggle_pause(icon, item):
        engine.toggle_pause()

    def calibrate(icon, item):
        engine.request_calibration()

    def toggle_autostart(icon, item):
        autostart.set_enabled(not autostart.enabled())

    def quit_app(icon, item):
        engine.stop()
        engine.join(timeout=3)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: "Reprendre" if engine.paused else "Pause  (Ctrl+Alt+G)",
            toggle_pause,
            default=True,
        ),
        pystray.MenuItem("Calibrer les écrans", calibrate),
        pystray.MenuItem(
            "Lancer au démarrage de Windows",
            toggle_autostart,
            checked=lambda item: autostart.enabled(),
            enabled=lambda item: autostart.available(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem("Quitter", quit_app),
    )
    icon = pystray.Icon("gazefocus", _icon_image(eng.PAUSED), "gazefocus", menu)

    def setup(icon):
        icon.visible = True
        engine.start()

    icon.run(setup)

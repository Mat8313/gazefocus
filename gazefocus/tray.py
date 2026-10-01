"""Icône de la zone de notification et son menu."""
import pystray
from PIL import Image, ImageDraw

from . import autostart, engine as eng, settings_ui
from .i18n import t

COLORS = {
    eng.ACTIVE: (80, 220, 120),
    eng.PAUSED: (150, 150, 150),
    eng.SINGLE_SCREEN: (150, 150, 150),
    eng.CALIBRATING: (90, 160, 255),
    eng.NEEDS_CALIBRATION: (255, 180, 60),
    eng.UNAVAILABLE: (255, 180, 60),
    eng.ERROR: (235, 80, 80),
}
LABELS = {
    eng.ACTIVE: t("actif", "active"),
    eng.PAUSED: t("en pause", "paused"),
    eng.SINGLE_SCREEN: t("un seul écran, rien à faire", "single screen, nothing to do"),
    eng.CALIBRATING: t("calibration en cours", "calibrating"),
    eng.NEEDS_CALIBRATION: t("calibration nécessaire", "calibration needed"),
    eng.UNAVAILABLE: t("caméra indisponible, nouvel essai en cours",
                       "camera unavailable, retrying"),
    eng.ERROR: t("erreur", "error"),
}


def _icon_image(state) -> Image.Image:
    """Un œil stylisé dont l'iris prend la couleur de l'état."""
    image = Image.new("RGBA", (64, 64), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.ellipse((2, 14, 62, 50), fill=(245, 245, 245), outline=(40, 40, 40), width=3)
    draw.ellipse((20, 20, 44, 44), fill=COLORS[state])
    draw.ellipse((27, 27, 37, 37), fill=(20, 20, 20))
    return image


def run(config):
    def on_state(state, detail=""):
        icon.icon = _icon_image(state)
        icon.title = f"gazefocus : {LABELS[state]}"
        icon.update_menu()
        if state in (eng.ERROR, eng.UNAVAILABLE):
            icon.notify(detail or LABELS[state], "gazefocus")
        elif state == eng.NEEDS_CALIBRATION:
            icon.notify(t("Calibration annulée. Relance-la depuis le menu.",
                          "Calibration cancelled. Start it again from the menu."), "gazefocus")

    def on_notice(message):
        icon.notify(message, "gazefocus")

    engine = eng.Engine(config, on_state, on_notice)

    def toggle_pause(icon, item):
        engine.toggle_pause()

    def calibrate(icon, item):
        engine.request_calibration()

    def open_settings(icon, item):
        settings_ui.show(engine.config, engine.apply_config)

    def toggle_autostart(icon, item):
        autostart.set_enabled(not autostart.enabled())

    def quit_app(icon, item):
        engine.stop()
        engine.join(timeout=3)
        icon.stop()

    menu = pystray.Menu(
        pystray.MenuItem(
            lambda item: (t("Reprendre", "Resume") if engine.paused
                          else t("Pause  (Ctrl+Alt+G)", "Pause  (Ctrl+Alt+G)")),
            toggle_pause,
            default=True,
        ),
        pystray.MenuItem(t("Calibrer les écrans", "Calibrate screens"), calibrate),
        pystray.MenuItem(t("Réglages…", "Settings…"), open_settings),
        pystray.MenuItem(
            t("Lancer au démarrage de Windows", "Start with Windows"),
            toggle_autostart,
            checked=lambda item: autostart.enabled(),
            enabled=lambda item: autostart.available(),
        ),
        pystray.Menu.SEPARATOR,
        pystray.MenuItem(t("Quitter", "Quit"), quit_app),
    )
    icon = pystray.Icon("gazefocus", _icon_image(eng.PAUSED), "gazefocus", menu)

    def setup(icon):
        icon.visible = True
        engine.start()

    icon.run(setup)

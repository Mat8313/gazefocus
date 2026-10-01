"""Thread d'arrière-plan : observe (caméra, fenêtres, clavier) et applique.

Les décisions elles-mêmes sont dans `brain.py`, qui ne touche pas à Windows.
"""
import threading
import time

import win32api
import win32con
import win32gui

from . import calibration, overlay, winfocus
from .brain import Brain, DriftMonitor, Pacer, World
from .gaze import GazeModel, profile_key
from .i18n import t
from .log import log
from .overlay import Overlay
from .tracker import HeadTracker

HOTKEY_ID = 1
SLOW_CHECK_INTERVAL = 1.0   # écrans branchés, session verrouillée
CAMERA_RETRY_INTERVAL = 5.0
SAVE_EVERY = 20             # échantillons appris entre deux sauvegardes

ACTIVE, PAUSED, CALIBRATING, NEEDS_CALIBRATION, SINGLE_SCREEN, UNAVAILABLE, ERROR = (
    "active", "paused", "calibrating", "needs_calibration", "single_screen",
    "unavailable", "error",
)


def _pump_messages() -> bool:
    """Traite les messages Windows du thread ; vrai si Ctrl+Alt+G a été pressé.

    Le contour (overlay) est une vraie fenêtre : sans cette boucle, elle ne se
    redessinerait jamais.
    """
    pressed = False
    while True:
        found, message = win32gui.PeekMessage(None, 0, 0, win32con.PM_REMOVE)
        if not found:
            return pressed
        if message[1] == win32con.WM_HOTKEY:
            pressed = True
        else:
            win32gui.TranslateMessage(message)
            win32gui.DispatchMessage(message)


class Engine(threading.Thread):
    """Piloté depuis l'icône de la zone de notification via les méthodes publiques."""

    def __init__(self, config, on_state=None, on_notice=None):
        super().__init__(daemon=True)
        self.config = config
        self.on_state = on_state or (lambda state, detail="": None)
        self.on_notice = on_notice or (lambda message: None)
        self.state = PAUSED
        self.paused = False
        self._calibrate = threading.Event()
        self._reload = threading.Event()
        self._quit = threading.Event()

        self.tracker = None
        self.model = GazeModel(use_eyes=config.use_eyes)
        self.monitors = []
        self.inputs = None
        self.drift = DriftMonitor()
        self.pacer = Pacer()
        self._unsaved = 0
        self._apply_reload()

    # --- commandes appelées depuis le thread de l'icône ---

    def toggle_pause(self):
        self.paused = not self.paused

    def request_calibration(self):
        self._calibrate.set()

    def apply_config(self, config):
        self.config = config
        self._reload.set()

    def stop(self):
        self._quit.set()

    # --- boucle ---

    def _set_state(self, state, detail=""):
        if state != ACTIVE:
            self.overlay.hide()
        if state != self.state:
            log.info("état : %s %s", state, detail)
            self.state = state
            self.on_state(state, detail)

    def _close_tracker(self):
        if self.tracker:
            self.tracker.close()
            self.tracker = None

    def _save_model(self):
        if self._unsaved:
            self.model.save()
            self._unsaved = 0

    def _apply_reload(self):
        config = self.config
        if self.tracker and self.tracker.camera != config.camera:
            self._close_tracker()
        self.model.use_eyes = config.use_eyes
        self.model.invalidate()
        self.brain = Brain(config, self.model, winfocus.top_window_on, self._window_at)

    def _window_at(self, monitor_name, uv):
        monitor = next(m for m in self.monitors if m.name == monitor_name)
        point = monitor.from_uv(uv)
        return winfocus.window_at(point) if monitor.contains(point) else None

    def _refresh_monitors(self):
        """Relu régulièrement : chaque disposition d'écrans a sa calibration."""
        self.monitors = winfocus.list_monitors()
        key = profile_key(self.monitors)
        if key != self.model.profile:
            self._save_model()
            names = [m.name for m in self.monitors]
            self.model = GazeModel.load(self.config.use_eyes, key, names)
            log.info("disposition : %d écran(s), calibrée : %s",
                     len(names), self.model.covers(names))
            self.drift.clear()
            self._apply_reload()

    def run(self):
        # Le raccourci doit être enregistré dans le thread qui lit ses messages.
        winfocus.user32.RegisterHotKey(
            None, HOTKEY_ID, win32con.MOD_CONTROL | win32con.MOD_ALT, ord("G")
        )
        self.overlay = Overlay()
        try:
            self._loop()
        except Exception as error:
            log.exception("Le moteur s'est arrêté")
            self._set_state(ERROR, f"{type(error).__name__}: {error}")
        finally:
            self.overlay.close()
            winfocus.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._close_tracker()
            self._save_model()

    def _loop(self):
        locked = False
        last_slow_check = retry_at = 0.0
        while not self._quit.is_set():
            started = time.monotonic()
            if _pump_messages():
                self.toggle_pause()
            if self._reload.is_set():
                self._reload.clear()
                self._apply_reload()

            if started - last_slow_check >= SLOW_CHECK_INTERVAL:
                last_slow_check = started
                locked = winfocus.session_locked()
                self._refresh_monitors()
            names = [m.name for m in self.monitors]

            # Avec un seul écran, il n'y a rien à faire sauf en mode fenêtres.
            single = len(names) < 2 and not self.config.same_screen
            if (self.paused or locked or single) and not self._calibrate.is_set():
                # Au repos, on libère la caméra.
                self._close_tracker()
                if single and not self.paused:
                    self._set_state(SINGLE_SCREEN)
                elif self.state != NEEDS_CALIBRATION:
                    self._set_state(PAUSED)
                time.sleep(0.2)
                continue

            try:
                if self.tracker is None:
                    if started < retry_at:
                        time.sleep(0.2)
                        continue
                    self.tracker = HeadTracker(self.config.camera)
                    self.inputs = winfocus.InputMonitor(time.monotonic())

                if self._calibrate.is_set() or not self.model.covers(names):
                    self._calibrate.clear()
                    self._set_state(CALIBRATING)
                    done = calibration.run(self.tracker, self.monitors, self.model)
                    log.info("calibration : %s", "terminée" if done else "annulée")
                    if not self.model.covers(names):
                        self.paused = True
                        self._set_state(NEEDS_CALIBRATION)
                        continue
                    if done:
                        self.paused = False
                        self.drift.clear()
                    self._apply_reload()
                    self.inputs = winfocus.InputMonitor(time.monotonic())
                    continue

                raw = self.tracker.read()
            except Exception as error:
                # Caméra débranchée, prise par une autre app, ou modèle
                # introuvable hors ligne : on réessaie plus tard.
                if self.state != UNAVAILABLE:
                    log.warning("caméra indisponible", exc_info=True)
                self._close_tracker()
                retry_at = time.monotonic() + CAMERA_RETRY_INTERVAL
                self._set_state(UNAVAILABLE, str(error))
                continue

            self._set_state(ACTIVE)
            try:
                self._step(raw, names)
            except win32gui.error as error:
                # Écran de verrouillage ou invite d'élévation : Windows refuse
                # alors de répondre (souris, fenêtres). Ce n'est pas une panne :
                # on saute cette image et on revérifie le verrouillage tout de suite.
                log.info("Windows a refusé un appel (%s), nouvelle vérification", error.funcname)
                last_slow_check = 0.0
                time.sleep(0.2)
                continue
            now = time.monotonic()
            time.sleep(max(0.0, self.pacer.interval(raw, now) - (now - started)))

    def _step(self, raw, names):
        """Observe le monde, demande au cerveau, applique."""
        config, inputs = self.config, self.inputs
        now = time.monotonic()
        inputs.poll(now)
        foreground = win32gui.GetForegroundWindow()
        if raw and inputs.clicked:
            self._on_click(raw)

        outcome = self.brain.step(World(
            raw=raw,
            names=names,
            foreground=foreground,
            current=winfocus.monitor_of_window(foreground),
            process=winfocus.process_name(foreground) if foreground else "",
            now=now,
            since_mouse=now - inputs.last_mouse,
            since_key=now - inputs.last_key,
        ))

        if outcome.focus and winfocus.focus_window(outcome.focus):
            foreground = outcome.focus
            if config.move_cursor:
                winfocus.move_cursor_to(outcome.focus)
                inputs.sync_cursor()

        if config.show_highlight and outcome.looked:
            color = overlay.FOCUSED if outcome.looked == foreground else overlay.PENDING
            self.overlay.show(winfocus.window_bounds(outcome.looked), color)
        else:
            self.overlay.hide()

    def _on_click(self, raw):
        """Un clic dit où tu regardes : on mesure l'erreur, puis on apprend."""
        cursor = win32api.GetCursorPos()
        monitor = next((m for m in self.monitors if m.contains(cursor)), None)
        if monitor is None:
            return
        uv = monitor.to_uv(cursor)
        error = self.model.click_error(monitor.name, uv, raw)
        if error is None:
            return
        if self.drift.add(error):
            log.info("dérive détectée")
            self.on_notice(t(
                "La précision a baissé. As-tu bougé ? Recalibre depuis le menu.",
                "Accuracy has dropped. Did you move? Recalibrate from the menu.",
            ))
        if self.config.learn_from_clicks and self.model.learn(monitor.name, uv, raw):
            self._unsaved += 1
            if self._unsaved >= SAVE_EVERY:
                self._save_model()

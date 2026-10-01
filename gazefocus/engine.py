"""Thread d'arrière-plan : caméra, décision et bascule de focus."""
import threading
import time

import win32api
import win32con
import win32gui

from . import calibration, winfocus
from .config import WINDOW_MIN_DWELL
from .decision import SwitchDecider
from .gaze import GazeModel
from .tracker import HeadTracker

HOTKEY_ID = 1
FRAME_INTERVAL = 1 / 15
SLOW_CHECK_INTERVAL = 1.0   # écrans branchés, session verrouillée
CAMERA_RETRY_INTERVAL = 5.0
SAVE_EVERY = 20             # échantillons appris entre deux sauvegardes

ACTIVE, PAUSED, CALIBRATING, NEEDS_CALIBRATION, UNAVAILABLE, ERROR = (
    "active", "paused", "calibrating", "needs_calibration", "unavailable", "error"
)


def _hotkey_pressed() -> bool:
    """Vide la file de messages du thread et signale un appui sur Ctrl+Alt+G."""
    pressed = False
    while True:
        found, _ = win32gui.PeekMessage(
            None, win32con.WM_HOTKEY, win32con.WM_HOTKEY, win32con.PM_REMOVE
        )
        if not found:
            return pressed
        pressed = True


class Engine(threading.Thread):
    """Piloté depuis l'icône de la zone de notification via les méthodes publiques."""

    def __init__(self, config, on_state=None):
        super().__init__(daemon=True)
        self.config = config
        self.on_state = on_state or (lambda state, detail="": None)
        self.state = PAUSED
        self.paused = False
        self._calibrate = threading.Event()
        self._reload = threading.Event()
        self._quit = threading.Event()
        self._reload.set()

        self.tracker = None
        self.model = GazeModel.load(config.use_eyes)
        self.monitors = []
        self.inputs = None
        self._unsaved = 0

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
        if state != self.state:
            self.state = state
            self.on_state(state, detail)

    def _close_tracker(self):
        if self.tracker:
            self.tracker.close()
            self.tracker = None

    def _apply_reload(self):
        config = self.config
        if self.tracker and self.tracker.camera != config.camera:
            self._close_tracker()
        self.model.use_eyes = config.use_eyes
        self.model.invalidate()
        self.screen_decider = SwitchDecider(config.switching())
        self.window_decider = SwitchDecider(config.switching(WINDOW_MIN_DWELL))

    def run(self):
        # Le raccourci doit être enregistré dans le thread qui lit ses messages.
        winfocus.user32.RegisterHotKey(
            None, HOTKEY_ID, win32con.MOD_CONTROL | win32con.MOD_ALT, ord("G")
        )
        try:
            self._loop()
        except Exception as error:
            self._set_state(ERROR, f"{type(error).__name__}: {error}")
        finally:
            winfocus.user32.UnregisterHotKey(None, HOTKEY_ID)
            self._close_tracker()
            if self._unsaved:
                self.model.save()

    def _loop(self):
        locked = False
        last_slow_check = retry_at = 0.0
        while not self._quit.is_set():
            started = time.monotonic()
            if _hotkey_pressed():
                self.toggle_pause()
            if self._reload.is_set():
                self._reload.clear()
                self._apply_reload()

            if started - last_slow_check >= SLOW_CHECK_INTERVAL:
                last_slow_check = started
                locked = winfocus.session_locked()
                # Relu régulièrement : un écran peut être branché à tout moment.
                self.monitors = winfocus.list_monitors()
            names = [m.name for m in self.monitors]

            if (self.paused or locked) and not self._calibrate.is_set():
                # En pause ou session verrouillée, on libère la caméra.
                self._close_tracker()
                if self.state != NEEDS_CALIBRATION:
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
                    if not self.model.covers(names):
                        self.paused = True
                        self._set_state(NEEDS_CALIBRATION)
                        continue
                    if done:
                        self.paused = False
                    self._apply_reload()
                    self.inputs = winfocus.InputMonitor(time.monotonic())
                    continue

                raw = self.tracker.read()
            except Exception as error:
                # Caméra débranchée, prise par une autre app, ou modèle
                # introuvable hors ligne : on réessaie plus tard.
                self._close_tracker()
                retry_at = time.monotonic() + CAMERA_RETRY_INTERVAL
                self._set_state(UNAVAILABLE, str(error))
                continue

            self._set_state(ACTIVE)
            self._step(raw, names)
            time.sleep(max(0.0, FRAME_INTERVAL - (time.monotonic() - started)))

    def _step(self, raw, names):
        config, inputs, model = self.config, self.inputs, self.model
        now = time.monotonic()
        inputs.poll(now)
        since_mouse, since_key = now - inputs.last_mouse, now - inputs.last_key
        foreground = win32gui.GetForegroundWindow()
        current = winfocus.monitor_of_window(foreground)
        target = model.classify(raw, names, current) if raw else None

        if raw and inputs.clicked and config.learn_from_clicks:
            self._learn_from_click(raw, names)

        switch_to = self.screen_decider.update(target, current, now, since_mouse, since_key)
        window = None
        if switch_to:
            window = winfocus.top_window_on(switch_to)
        elif config.same_screen and target and target == current:
            window = self.window_decider.update(
                self._window_looked_at(raw, target), foreground, now, since_mouse, since_key
            )
        else:
            self.window_decider.update(None, foreground, now, since_mouse, since_key)

        if window and winfocus.focus_window(window) and config.move_cursor:
            winfocus.move_cursor_to(window)
            inputs.sync_cursor()

    def _learn_from_click(self, raw, names):
        cursor = win32api.GetCursorPos()
        monitor = next((m for m in self.monitors if m.contains(cursor)), None)
        if monitor and self.model.learn(monitor.name, monitor.to_uv(cursor), raw, names):
            self._unsaved += 1
            if self._unsaved >= SAVE_EVERY:
                self.model.save()
                self._unsaved = 0

    def _window_looked_at(self, raw, monitor_name):
        uv = self.model.locate(raw, monitor_name)
        if uv is None:
            return None
        monitor = next(m for m in self.monitors if m.name == monitor_name)
        point = monitor.from_uv(uv)
        return winfocus.window_at(point) if monitor.contains(point) else None

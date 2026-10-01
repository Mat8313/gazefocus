"""Thread d'arrière-plan : caméra, décision et bascule de focus."""
import threading
import time

import win32con
import win32gui

from . import calibration, winfocus
from .decision import Settings, SwitchDecider
from .tracker import HeadTracker

HOTKEY_ID = 1
FRAME_INTERVAL = 1 / 15

ACTIVE, PAUSED, CALIBRATING, NEEDS_CALIBRATION, ERROR = (
    "active", "paused", "calibrating", "needs_calibration", "error"
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

    def __init__(self, camera=0, settings=None, on_state=None):
        super().__init__(daemon=True)
        self.camera = camera
        self.settings = settings or Settings()
        self.on_state = on_state or (lambda state, detail="": None)
        self.state = PAUSED
        self.paused = False
        self._calibrate = threading.Event()
        self._quit = threading.Event()

    def toggle_pause(self):
        self.paused = not self.paused

    def request_calibration(self):
        self._calibrate.set()

    def stop(self):
        self._quit.set()

    def _set_state(self, state, detail=""):
        if state != self.state or detail:
            self.state = state
            self.on_state(state, detail)

    def run(self):
        # Le raccourci doit être enregistré dans le thread qui lit ses messages.
        winfocus.user32.RegisterHotKey(
            None, HOTKEY_ID, win32con.MOD_CONTROL | win32con.MOD_ALT, ord("G")
        )
        tracker = None
        try:
            while not self._quit.is_set():
                started = time.monotonic()
                if _hotkey_pressed():
                    self.toggle_pause()

                if self.paused and not self._calibrate.is_set():
                    if tracker:
                        # En pause, on libère la caméra : le voyant s'éteint.
                        tracker.close()
                        tracker = None
                    if self.state not in (NEEDS_CALIBRATION, ERROR):
                        self._set_state(PAUSED)
                    time.sleep(0.1)
                    continue

                if tracker is None:
                    try:
                        tracker = HeadTracker(self.camera)
                    except Exception as error:
                        self.paused = True
                        self._calibrate.clear()
                        self._set_state(ERROR, str(error))
                        continue
                    monitors = winfocus.list_monitors()
                    names = {m.name for m in monitors}
                    centers = calibration.load()
                    decider = SwitchDecider(self.settings)
                    inputs = winfocus.InputMonitor(time.monotonic())
                    if set(centers) != names:
                        self._calibrate.set()

                if self._calibrate.is_set():
                    self._calibrate.clear()
                    self._set_state(CALIBRATING)
                    centers = calibration.run(tracker, monitors) or centers
                    if set(centers) != names:
                        self.paused = True
                        self._set_state(NEEDS_CALIBRATION)
                        continue
                    self.paused = False
                    decider = SwitchDecider(self.settings)

                self._set_state(ACTIVE)
                pose = tracker.read()
                now = time.monotonic()
                inputs.poll(now)
                current = winfocus.monitor_of_window(win32gui.GetForegroundWindow())
                target = calibration.classify(pose, centers, current) if pose else None
                switch_to = decider.update(
                    target, current, now, now - inputs.last_mouse, now - inputs.last_key
                )
                if switch_to:
                    hwnd = winfocus.top_window_on(switch_to)
                    if hwnd:
                        winfocus.focus_window(hwnd)

                time.sleep(max(0.0, FRAME_INTERVAL - (time.monotonic() - started)))
        except Exception as error:
            self._set_state(ERROR, str(error))
        finally:
            winfocus.user32.UnregisterHotKey(None, HOTKEY_ID)
            if tracker:
                tracker.close()

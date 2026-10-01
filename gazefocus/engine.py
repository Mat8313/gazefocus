"""Thread d'arrière-plan : caméra, décision et bascule de focus."""
import statistics
import threading
import time
from collections import deque

import win32api
import win32con
import win32gui

from . import calibration, overlay, winfocus
from .config import WINDOW_MIN_DWELL
from .decision import SwitchDecider
from .gaze import GazeModel, profile_key
from .i18n import t
from .overlay import Overlay
from .tracker import HeadTracker

HOTKEY_ID = 1
ACTIVE_INTERVAL = 1 / 20    # quand le regard bouge
RESTING_INTERVAL = 1 / 5    # quand il est posé : quatre fois moins de calcul
REST_AFTER = 2.0            # secondes sans mouvement avant de ralentir
# Mouvement minimal pour repasser en cadence rapide : degrés pour la tête,
# largeurs d'œil pour les iris. Au-dessus du tremblement résiduel du filtre.
MOTION_HEAD, MOTION_EYES = 1.5, 0.03
SLOW_CHECK_INTERVAL = 1.0   # écrans branchés, session verrouillée
CAMERA_RETRY_INTERVAL = 5.0
SAVE_EVERY = 20             # échantillons appris entre deux sauvegardes
# Dérive : si l'erreur médiane des 20 derniers clics dépasse un quart d'écran,
# la calibration ne correspond plus à ta position.
DRIFT_WINDOW, DRIFT_THRESHOLD = 20, 0.25

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


def _moved(pose, reference) -> bool:
    if pose is None or reference is None:
        return pose is not reference
    return (
        max(abs(pose[i] - reference[i]) for i in (0, 1)) > MOTION_HEAD
        or max(abs(pose[i] - reference[i]) for i in (2, 3)) > MOTION_EYES
    )


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
        self._reload.set()

        self.tracker = None
        self.model = GazeModel(use_eyes=config.use_eyes)
        self.monitors = []
        self.inputs = None
        self._unsaved = 0
        self._click_errors = deque(maxlen=DRIFT_WINDOW)
        self._reference_pose = None
        self._last_motion = 0.0

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
        self.screen_decider = SwitchDecider(config.switching())
        self.window_decider = SwitchDecider(config.switching(WINDOW_MIN_DWELL))

    def _refresh_monitors(self):
        """Relu régulièrement : chaque disposition d'écrans a sa calibration."""
        self.monitors = winfocus.list_monitors()
        key = profile_key(self.monitors)
        if key != self.model.profile:
            self._save_model()
            names = [m.name for m in self.monitors]
            self.model = GazeModel.load(self.config.use_eyes, key, names)
            self._click_errors.clear()

    def run(self):
        # Le raccourci doit être enregistré dans le thread qui lit ses messages.
        winfocus.user32.RegisterHotKey(
            None, HOTKEY_ID, win32con.MOD_CONTROL | win32con.MOD_ALT, ord("G")
        )
        self.overlay = Overlay()
        try:
            self._loop()
        except Exception as error:
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
                    if not self.model.covers(names):
                        self.paused = True
                        self._set_state(NEEDS_CALIBRATION)
                        continue
                    if done:
                        self.paused = False
                        self._click_errors.clear()
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

            now = time.monotonic()
            if _moved(raw, self._reference_pose):
                self._reference_pose, self._last_motion = raw, now
            resting = now - self._last_motion > REST_AFTER
            interval = RESTING_INTERVAL if resting else ACTIVE_INTERVAL
            time.sleep(max(0.0, interval - (now - started)))

    def _step(self, raw, names):
        config, inputs, model = self.config, self.inputs, self.model
        now = time.monotonic()
        inputs.poll(now)
        since_mouse, since_key = now - inputs.last_mouse, now - inputs.last_key
        foreground = win32gui.GetForegroundWindow()
        current = winfocus.monitor_of_window(foreground)
        target = model.classify(raw, names, current) if raw else None

        if raw and inputs.clicked:
            self._on_click(raw)

        if foreground and winfocus.process_name(foreground) in config.excluded:
            # App exclue au premier plan (jeu, visio...) : on ne touche à rien.
            target = None

        # Fenêtre que l'app pense que tu regardes.
        other_screen = bool(target) and target != current
        if other_screen:
            looked = winfocus.top_window_on(target)
        elif target and config.same_screen:
            looked = self._window_looked_at(raw, target)
        else:
            looked = foreground if target else None

        switch_to = self.screen_decider.update(target, current, now, since_mouse, since_key)
        same_screen_candidate = looked if config.same_screen and not other_screen else None
        window = self.window_decider.update(
            same_screen_candidate, foreground, now, since_mouse, since_key
        )
        if switch_to:
            window = looked

        if window and winfocus.focus_window(window):
            foreground = window
            if config.move_cursor:
                winfocus.move_cursor_to(window)
                inputs.sync_cursor()

        if config.show_highlight and looked:
            color = overlay.FOCUSED if looked == foreground else overlay.PENDING
            self.overlay.show(winfocus.window_bounds(looked), color)
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
        self._click_errors.append(error)
        if (len(self._click_errors) == DRIFT_WINDOW
                and statistics.median(self._click_errors) > DRIFT_THRESHOLD):
            self._click_errors.clear()  # prochain avertissement dans 20 clics au plus tôt
            self.on_notice(t(
                "La précision a baissé. As-tu bougé ? Recalibre depuis le menu.",
                "Accuracy has dropped. Did you move? Recalibrate from the menu.",
            ))
        if self.config.learn_from_clicks and self.model.learn(monitor.name, uv, raw):
            self._unsaved += 1
            if self._unsaved >= SAVE_EVERY:
                self._save_model()

    def _window_looked_at(self, raw, monitor_name):
        uv = self.model.locate(raw, monitor_name)
        monitor = next(m for m in self.monitors if m.name == monitor_name)
        point = monitor.from_uv(uv)
        return winfocus.window_at(point) if monitor.contains(point) else None

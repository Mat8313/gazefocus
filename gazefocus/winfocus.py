"""Tout ce qui touche à Win32 : écrans, fenêtres, focus, activité souris/clavier."""
import ctypes
from ctypes import wintypes
from dataclasses import dataclass

import win32api
import win32con
import win32gui
import win32process

user32 = ctypes.windll.user32
DWMWA_CLOAKED = 14


def enable_dpi_awareness():
    """Sans ça, Windows nous ment sur les coordonnées des écrans mis à l'échelle."""
    try:
        ctypes.windll.shcore.SetProcessDpiAwareness(2)
    except (AttributeError, OSError):
        user32.SetProcessDPIAware()


def acquire_single_instance() -> bool:
    """False si gazefocus tourne déjà (démarrage auto + lancement manuel)."""
    global _instance_mutex
    _instance_mutex = ctypes.windll.kernel32.CreateMutexW(None, False, "gazefocus-single-instance")
    return ctypes.windll.kernel32.GetLastError() != 183  # ERROR_ALREADY_EXISTS


@dataclass(frozen=True)
class Monitor:
    name: str
    left: int
    top: int
    right: int
    bottom: int

    @property
    def center(self):
        return (self.left + self.right) // 2, (self.top + self.bottom) // 2


def list_monitors() -> list[Monitor]:
    monitors = []
    for handle, _, _ in win32api.EnumDisplayMonitors():
        info = win32api.GetMonitorInfo(handle)
        monitors.append(Monitor(info["Device"], *info["Monitor"]))
    return sorted(monitors, key=lambda m: (m.left, m.top))


def monitor_of_window(hwnd) -> str | None:
    if not hwnd:
        return None
    handle = win32api.MonitorFromWindow(hwnd, win32con.MONITOR_DEFAULTTONEAREST)
    return win32api.GetMonitorInfo(handle)["Device"]


def _is_cloaked(hwnd) -> bool:
    # Les apps UWP suspendues et les fenêtres d'autres bureaux virtuels sont
    # "visibles" pour Win32 mais masquées par DWM.
    cloaked = wintypes.DWORD()
    ctypes.windll.dwmapi.DwmGetWindowAttribute(
        wintypes.HWND(hwnd), DWMWA_CLOAKED, ctypes.byref(cloaked), ctypes.sizeof(cloaked)
    )
    return cloaked.value != 0


def is_switchable(hwnd) -> bool:
    if not win32gui.IsWindowVisible(hwnd) or win32gui.IsIconic(hwnd):
        return False
    if not win32gui.GetWindowText(hwnd):
        return False
    if win32gui.GetWindowLong(hwnd, win32con.GWL_EXSTYLE) & win32con.WS_EX_TOOLWINDOW:
        return False
    return not _is_cloaked(hwnd)


def top_window_on(monitor_name: str):
    """Fenêtre la plus haute sur cet écran, donc la dernière utilisée dessus.

    EnumWindows parcourt les fenêtres dans l'ordre d'empilement (z-order).
    """
    found = []

    def visit(hwnd, _):
        if is_switchable(hwnd) and monitor_of_window(hwnd) == monitor_name:
            found.append(hwnd)
            return False
        return True

    try:
        win32gui.EnumWindows(visit, None)
    except win32gui.error:
        pass  # pywin32 lève une erreur quand le callback interrompt l'énumération
    return found[0] if found else None


def focus_window(hwnd) -> bool:
    """Donne le focus clavier à hwnd, sans clic synthétique."""
    foreground = win32gui.GetForegroundWindow()
    if foreground == hwnd:
        return True
    # Windows refuse SetForegroundWindow à un processus d'arrière-plan. En se
    # rattachant à la file d'entrée de la fenêtre active, on hérite de son droit.
    current = win32api.GetCurrentThreadId()
    target = win32process.GetWindowThreadProcessId(foreground)[0] if foreground else 0
    attached = False
    try:
        if target and target != current:
            attached = bool(user32.AttachThreadInput(current, target, True))
        user32.BringWindowToTop(hwnd)
        user32.SetForegroundWindow(hwnd)
    finally:
        if attached:
            user32.AttachThreadInput(current, target, False)
    return win32gui.GetForegroundWindow() == hwnd


class _LASTINPUTINFO(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class InputMonitor:
    """Sait depuis combien de temps la souris et le clavier sont au repos."""

    def __init__(self, now: float):
        self.last_mouse = self.last_key = now - 60
        self._cursor = win32api.GetCursorPos()
        self._tick = self._input_tick()

    @staticmethod
    def _input_tick() -> int:
        info = _LASTINPUTINFO(cbSize=ctypes.sizeof(_LASTINPUTINFO))
        user32.GetLastInputInfo(ctypes.byref(info))
        return info.dwTime

    def poll(self, now: float):
        cursor, tick = win32api.GetCursorPos(), self._input_tick()
        buttons = any(
            user32.GetAsyncKeyState(vk) & 0x8000
            for vk in (win32con.VK_LBUTTON, win32con.VK_RBUTTON, win32con.VK_MBUTTON)
        )
        if cursor != self._cursor or buttons:
            self.last_mouse = now
        elif tick != self._tick:
            # Une entrée a eu lieu sans que la souris bouge : c'est le clavier.
            self.last_key = now
        self._cursor, self._tick = cursor, tick

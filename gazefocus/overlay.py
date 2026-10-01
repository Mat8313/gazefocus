"""Contour affiché autour de la fenêtre que l'app pense que tu regardes."""
import win32api
import win32con
import win32gui

CLASS_NAME = "gazefocus-overlay"
THICKNESS = 4
FOCUSED = (80, 220, 120)   # vert : cette fenêtre a déjà le focus
PENDING = (255, 170, 40)   # orange : regardée, bascule pas encore faite


class Overlay:
    """Fenêtre sans fond, toujours au-dessus, que la souris traverse.

    Doit être créée et utilisée dans un thread qui traite ses messages Windows.
    """

    def __init__(self, handlers=None):
        """handlers : {message Windows: fonction}, pour les messages que le
        propriétaire veut recevoir par cette fenêtre (c'est la seule de l'app)."""
        self._shown = None
        self._brush = None
        window_class = win32gui.WNDCLASS()
        window_class.lpszClassName = CLASS_NAME
        window_class.lpfnWndProc = {win32con.WM_PAINT: self._paint, **(handlers or {})}
        window_class.hInstance = win32api.GetModuleHandle(None)
        win32gui.RegisterClass(window_class)
        style = (win32con.WS_EX_LAYERED | win32con.WS_EX_TRANSPARENT | win32con.WS_EX_TOPMOST
                 | win32con.WS_EX_TOOLWINDOW | win32con.WS_EX_NOACTIVATE)
        self.hwnd = win32gui.CreateWindowEx(
            style, CLASS_NAME, "", win32con.WS_POPUP, 0, 0, 0, 0, 0, 0,
            window_class.hInstance, None,
        )
        win32gui.SetLayeredWindowAttributes(self.hwnd, 0, 210, win32con.LWA_ALPHA)

    def _paint(self, hwnd, message, wparam, lparam):
        hdc, paint = win32gui.BeginPaint(hwnd)
        if self._brush:
            win32gui.FillRect(hdc, win32gui.GetClientRect(hwnd), self._brush)
        win32gui.EndPaint(hwnd, paint)
        return 0

    def show(self, rect, color):
        if (rect, color) == self._shown:
            return
        left, top, right, bottom = rect
        width, height = right - left, bottom - top
        # La fenêtre est réduite à un cadre : un rectangle moins son intérieur.
        frame = win32gui.CreateRectRgnIndirect((0, 0, width, height))
        inner = win32gui.CreateRectRgnIndirect(
            (THICKNESS, THICKNESS, width - THICKNESS, height - THICKNESS)
        )
        win32gui.CombineRgn(frame, frame, inner, win32con.RGN_DIFF)
        win32gui.DeleteObject(inner)
        win32gui.SetWindowRgn(self.hwnd, frame, True)  # Windows devient propriétaire de la région

        old = self._brush
        self._brush = win32gui.CreateSolidBrush(win32api.RGB(*color))
        if old:
            win32gui.DeleteObject(old)
        win32gui.SetWindowPos(
            self.hwnd, win32con.HWND_TOPMOST, left, top, width, height,
            win32con.SWP_NOACTIVATE | win32con.SWP_SHOWWINDOW,
        )
        win32gui.InvalidateRect(self.hwnd, None, True)
        self._shown = (rect, color)

    def hide(self):
        if self._shown:
            win32gui.ShowWindow(self.hwnd, win32con.SW_HIDE)
            self._shown = None

    def close(self):
        win32gui.DestroyWindow(self.hwnd)
        win32gui.UnregisterClass(CLASS_NAME, win32api.GetModuleHandle(None))

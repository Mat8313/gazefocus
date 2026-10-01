"""Point d'entrée : `python -m gazefocus calibrate` puis `python -m gazefocus run`."""
import argparse
import sys
import time

import cv2
import win32con
import win32gui

from . import calibration, winfocus
from .decision import Settings, SwitchDecider
from .tracker import HeadTracker

HOTKEY_ID = 1
FRAME_INTERVAL = 1 / 15


def hotkey_pressed() -> bool:
    """Vide la file de messages du thread et signale un appui sur Ctrl+Alt+G."""
    pressed = False
    while True:
        found, _ = win32gui.PeekMessage(
            None, win32con.WM_HOTKEY, win32con.WM_HOTKEY, win32con.PM_REMOVE
        )
        if not found:
            return pressed
        pressed = True


def run(tracker, monitors, settings, preview):
    centers = calibration.load()
    names = {m.name for m in monitors}
    if set(centers) != names:
        sys.exit("Calibration absente ou écrans modifiés : lance `python -m gazefocus calibrate`.")

    decider = SwitchDecider(settings)
    inputs = winfocus.InputMonitor(time.monotonic())
    winfocus.user32.RegisterHotKey(
        None, HOTKEY_ID, win32con.MOD_CONTROL | win32con.MOD_ALT, ord("G")
    )
    paused = False
    print("gazefocus actif. Ctrl+Alt+G : pause/reprise. Ctrl+C : quitter.")
    try:
        while True:
            started = time.monotonic()
            if hotkey_pressed():
                paused = not paused
                print("En pause" if paused else "Reprise")
            if paused:
                time.sleep(0.1)
                continue

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
                if hwnd and winfocus.focus_window(hwnd):
                    print(f"-> {switch_to} : {win32gui.GetWindowText(hwnd)[:60]}")

            if preview and tracker.frame is not None:
                label = f"{pose[0]:+.0f} / {pose[1]:+.0f}  {target}" if pose else "pas de visage"
                frame = tracker.frame
                cv2.putText(frame, label, (10, 30), cv2.FONT_HERSHEY_SIMPLEX,
                            0.7, (80, 220, 120), 2, cv2.LINE_AA)
                cv2.imshow("gazefocus", frame)
                cv2.waitKey(1)

            time.sleep(max(0.0, FRAME_INTERVAL - (time.monotonic() - started)))
    except KeyboardInterrupt:
        print("Arrêt.")
    finally:
        winfocus.user32.UnregisterHotKey(None, HOTKEY_ID)
        cv2.destroyAllWindows()


def main():
    parser = argparse.ArgumentParser(prog="gazefocus", description=__doc__)
    parser.add_argument("command", choices=["calibrate", "run"])
    parser.add_argument("--camera", type=int, default=0, help="index de la webcam")
    parser.add_argument("--preview", action="store_true", help="affiche la caméra et la pose")
    parser.add_argument("--dwell", type=float, default=Settings.dwell,
                        help="secondes à fixer un écran avant de basculer")
    args = parser.parse_args()

    winfocus.enable_dpi_awareness()
    monitors = winfocus.list_monitors()
    tracker = HeadTracker(args.camera)
    try:
        if args.command == "calibrate":
            centers = calibration.run(tracker, monitors)
            if centers is None:
                sys.exit("Calibration annulée.")
            for name, (yaw, pitch) in centers.items():
                print(f"{name}: yaw {yaw:+.1f}°, pitch {pitch:+.1f}°")
            print(f"Enregistré dans {calibration.CALIBRATION_PATH}")
        else:
            run(tracker, monitors, Settings(dwell=args.dwell), args.preview)
    finally:
        tracker.close()


if __name__ == "__main__":
    main()

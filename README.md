# gazefocus

[![Tests](https://github.com/Mat8313/gazefocus/actions/workflows/tests.yml/badge.svg)](https://github.com/Mat8313/gazefocus/actions/workflows/tests.yml)

[![gazefocus demo](docs/demo.gif)](docs/demo.mp4)

*Click the animation for the video with sound (23 seconds).*

**English** · [Français](README.fr.md)

Keyboard focus follows the screen you look at, on Windows. Turn towards your
other monitor and type: the last window you used on that screen already has
focus, no click needed.

The app runs in the background, with an icon in the notification area. Its
interface is in English or French, depending on your Windows language.

Everything runs locally: the webcam is analysed in memory with MediaPipe, and no
image is ever saved or sent. The only network request is the download of the
face model (about 4 MB) on first launch.

## Install

From the [Releases](https://github.com/Mat8313/gazefocus/releases) page, pick
one:

- `gazefocus-setup.exe`: installer that needs no administrator rights, adds a
  Start menu shortcut and uninstalls cleanly;
- `gazefocus-windows.zip`: unzip anywhere, then run `gazefocus.exe`.

No Python needed. Requires 64-bit Windows 10/11, a webcam and at least two
screens.

The executable is not signed, so Windows SmartScreen may show a warning on first
launch: "More info", then "Run anyway".

## Usage

On first launch, calibration starts by itself, in two steps:

1. Sitting as usual: on each screen, press Space, then follow with your eyes the
   dot that runs along the edges and through the middle, for 14 seconds.
2. Move your chair back about 25 cm (10 in) and do it again. This step teaches
   the app how distance changes the angles; press S to skip it.

Each screen layout (laptop alone, laptop plus external monitor...) keeps its own
calibration, picked up automatically when you plug back in.

Icon menu (right click):

- **Pause / Resume**: also by left-clicking the icon or with `Ctrl+Alt+G`.
  While paused, the camera is released.
- **Calibrate screens**: redo it if you move a screen or the webcam.
- **Settings…**: see below.
- **Start with Windows**: available in the `.exe` version.
- **Open the log**: errors and state changes, useful when reporting a bug. No
  window title or application name is ever written to it.
- **Quit**

Iris colour: green active, grey paused, blue calibrating, orange calibration
needed or camera unavailable, red error.

### Settings

| Setting | Default | Effect |
| --- | --- | --- |
| Camera | 0 | Index of the webcam to use |
| Dwell time | 0.3 s | How long you look at a screen before focus moves |
| Keep focus after a keystroke | 3 s | Focus never moves while you type |
| Keep focus after mouse use | 1.5 s | The mouse stays in charge |
| Refine with every click | on | Each click becomes a calibration sample |
| Move the pointer | off | The pointer goes to the window that gets focus |
| Use the eyes | on | Adds iris position; recalibrate after changing this |
| Windows on the same screen | off | Experimental: switch between neighbouring windows |
| Outline the looked-at window | off | Green if it has focus, orange if the switch is pending |
| Excluded apps | none | Focus never moves on its own in front of these (e.g. `vlc.exe`) |

Settings are stored in `%APPDATA%\gazefocus\config.json`.

## Run from source

Python 3.10 or later.

```
python -m venv .venv
.venv\Scripts\activate
pip install -r requirements.txt
python -m gazefocus
```

## Build the exe

```
pip install pyinstaller
.\build.ps1
```

The result is the `dist\gazefocus` folder (about 210 MB, mostly OpenCV and
MediaPipe). For the installer, with [Inno Setup](https://jrsoftware.org/isinfo.php):

```
iscc /DAppVersion=0.5.0 installer.iss
```

On GitHub, pushing a `vX.Y.Z` tag builds the zip and the installer and attaches
them to the release (`.github/workflows/release.yml`).

## How it works

1. `tracker.py`: MediaPipe estimates the orientation and position of the head
   and the offset of the irises within the eyes. A One Euro filter
   (`smoothing.py`) smooths it all: heavily at rest, lightly in motion.
2. `gaze.py`: each screen has "pose -> position" samples. A ridge regression per
   screen turns a pose into the point being looked at; the chosen screen is the
   one that point falls in, with a margin favouring the current screen to avoid
   flip-flopping. The weight of the eyes relative to the head is therefore
   learned per person. "Angle × distance" terms compensate for moving the chair
   back or forward.
3. `calibration.py` provides the initial samples (about 150 per screen); after
   that every click adds one, because you look where you click. The last 200
   clicks per screen are kept, recent ones weighing more.
4. `decision.py`: focus only moves after a sustained look, never while you type
   or use the mouse.
5. `winfocus.py`: the topmost window in the target screen's z-order gets focus
   through the Win32 API.
6. `brain.py` combines these decisions without ever calling Windows, which makes
   it testable; `engine.py` observes (camera, windows, keyboard) and applies, in
   a thread. `tray.py` handles the icon, `settings_ui.py` the settings window.

The app idles when the session is locked or when there is a single screen, and
retries every 5 seconds if the camera is unavailable. It processes 20 frames per
second while your gaze moves and 5 when it rests. If the error measured on your
last 20 clicks exceeds a quarter of a screen, a notification suggests
recalibrating. When several faces are visible, the one nearest to the camera is
tracked.

## Limitations

- Eye tracking stays approximate with an ordinary webcam: it depends on
  lighting, and reflective glasses degrade it.
- Switching between windows on the same screen needs a precision the webcam does
  not always provide; it suits two windows side by side.
- Windows started as administrator cannot receive focus from a normal process.

## Tests

```
pip install pytest
python -m pytest
```

## License

MIT, see [LICENSE](LICENSE).

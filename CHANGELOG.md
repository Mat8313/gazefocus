# Changelog

## 1.0.0

First stable version. This release is about finish, plus one fix found through the new log file.

- Application icon for the executable and the installer
- Version number shown in the icon tooltip, the menu and the log
- Menu entry that opens the project page
- The release build now fails if the tag and the app version disagree
- Fix: locking the session (Win+L) no longer stops the app; it pauses, releases
  the camera and resumes on unlock

## 0.5.1

- Log file in `%APPDATA%\gazefocus`, with an **Open the log** menu entry
- When several faces are visible, the nearest one is tracked
- README in English with a demo video; French version in `README.fr.md`
- The engine's decisions are covered by automated tests

## 0.5.0

- Distance compensation: optional second calibration pass from further back
- Notification when recent clicks show the calibration no longer fits
- Adaptive frame rate: 5 frames per second at rest, 20 in motion
- One calibration per screen layout; idle with a single screen
- English interface when Windows is not in French

## 0.4.0

- Installer that needs no administrator rights
- Camera read at 30 frames per second instead of 10 on some webcams
- Optional outline around the window being looked at
- List of excluded applications
- Automated tests and release builds on GitHub

## 0.3.0

- Pursuit calibration: follow a moving dot instead of confirming fixed points
- Gaze model learned per person, using head and eyes
- Adaptive smoothing, 720p capture

## 0.2.0

- Five-point calibration, refined by every click
- Settings window
- Options: pointer follows focus, eyes, windows on the same screen
- Pauses when the session is locked, retries when the camera is unavailable

## 0.1.0

- First version: focus follows the screen you face, notification-area icon,
  pause, calibration, start with Windows

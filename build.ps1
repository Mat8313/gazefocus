# Construit dist\gazefocus\gazefocus.exe (sans console).
# Prérequis : pip install -r requirements.txt pyinstaller
python -m PyInstaller --noconfirm --noconsole --name gazefocus `
    --collect-all mediapipe `
    --hidden-import pystray._win32 `
    run_gazefocus.py

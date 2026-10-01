# Construit dist\gazefocus\gazefocus.exe (sans console).
# Prérequis : pip install -r requirements.txt pyinstaller

# MediaPipe installe OpenCV 5 (contrib), deux fois plus lourd que nécessaire.
# On le remplace par OpenCV 4, qui suffit pour lire la webcam.
python -m pip uninstall -y opencv-contrib-python opencv-python
python -m pip install "opencv-python==4.11.0.86"

python -m PyInstaller --noconfirm gazefocus.spec

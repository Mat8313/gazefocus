# Recette PyInstaller : `python -m PyInstaller --noconfirm gazefocus.spec`
from PyInstaller.utils.hooks import collect_all

datas, binaries, hiddenimports = collect_all("mediapipe")
hiddenimports = [name for name in hiddenimports if "test" not in name]

a = Analysis(
    ["run_gazefocus.py"],
    datas=datas,
    binaries=binaries,
    hiddenimports=hiddenimports + ["pystray._win32"],
    # matplotlib et sounddevice restent : MediaPipe les importe au démarrage.
    excludes=["scipy", "IPython", "pytest"],
)

# Poids morts : le décodeur vidéo d'OpenCV (on ne lit que la webcam), le codec
# AVIF de Pillow et les fichiers de tests de MediaPipe.
UNUSED = ("opencv_videoio_ffmpeg", "_avif")
a.binaries = [b for b in a.binaries if not any(u in b[0] for u in UNUSED)]
a.datas = [
    d for d in a.datas
    if not any(u in d[0] for u in UNUSED) and "\\test\\" not in d[0] and "/test/" not in d[0]
]

pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, exclude_binaries=True, name="gazefocus", console=False,
          icon="gazefocus.ico")
COLLECT(exe, a.binaries, a.datas, name="gazefocus")

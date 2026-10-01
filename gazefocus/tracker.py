"""Webcam -> orientation et position de la tête, position des iris, via MediaPipe."""
import math
import os
import time
import urllib.request

# Sans ça, l'ouverture d'une caméra par Media Foundation prend plusieurs secondes.
os.environ.setdefault("OPENCV_VIDEOIO_MSMF_ENABLE_HW_TRANSFORMS", "0")

import cv2
import mediapipe as mp

from .config import DATA_DIR
from .smoothing import OneEuroFilter

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = DATA_DIR / "face_landmarker.task"

# (coin gauche, coin droit, centre de l'iris) de chaque œil, dans l'image.
EYES = ((33, 133, 468), (362, 263, 473))
BLACK_FRAMES_LIMIT = 30
# Gain du filtre par axe, adapté à l'unité de chacun : yaw et pitch en degrés,
# décalages d'iris en fraction de largeur d'œil, position de la tête en cm.
FILTER_BETA = (0.05, 0.05, 3.0, 3.0, 0.2, 0.2, 0.2)


class CameraError(RuntimeError):
    """La caméra ne fournit pas d'image (débranchée, ou prise par une autre app)."""


def ensure_model():
    """Télécharge le modèle une seule fois ; ensuite tout tourne hors ligne."""
    if not MODEL_PATH.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        tmp = MODEL_PATH.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL_PATH)
    return MODEL_PATH


def _eye_offsets(landmarks):
    """Décalage moyen des iris dans les yeux, en largeurs d'œil : (0, 0) = centré."""
    dx = dy = 0.0
    for left, right, iris in EYES:
        a, b, c = landmarks[left], landmarks[right], landmarks[iris]
        width = b.x - a.x
        if abs(width) < 1e-6:
            return 0.0, 0.0
        dx += (c.x - a.x) / width - 0.5
        dy += (c.y - (a.y + b.y) / 2) / width
    return dx / len(EYES), dy / len(EYES)


class HeadTracker:
    """Lit la caméra et renvoie une pose lissée. Aucune image n'est sauvegardée."""

    def __init__(self, camera: int = 0):
        self.camera = camera
        # Media Foundation d'abord : sur certaines webcams, DirectShow plafonne
        # à 10 images/s là où Media Foundation en fournit 30.
        self.cap = cv2.VideoCapture(camera, cv2.CAP_MSMF)
        if not self.cap.isOpened():
            self.cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise CameraError(f"Impossible d'ouvrir la caméra {camera}")
        # En 720p, un iris couvre deux fois plus de pixels qu'en 480p. Si la
        # caméra ne le propose pas, elle garde sa résolution la plus proche.
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 1280)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 720)
        self.cap.set(cv2.CAP_PROP_FPS, 30)

        vision = mp.tasks.vision
        options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self._filter = OneEuroFilter(min_cutoff=1.0, beta=FILTER_BETA)
        self._t0 = time.monotonic()
        self._last_ts = -1
        self._black = 0

    def read(self):
        """Renvoie la pose, ou None si aucun visage n'est visible.

        La pose est (yaw, pitch, œil x, œil y, tête x, tête y, tête z) : angles
        en degrés, yeux en largeurs d'œil, position en cm. Lève CameraError si
        la caméra ne répond plus.
        """
        ok, frame = self.cap.read()
        if not ok:
            raise CameraError("La caméra ne fournit plus d'image")
        # Quand une autre app tient la caméra, Windows livre des images noires.
        self._black = 0 if frame.any() else self._black + 1
        if self._black >= BLACK_FRAMES_LIMIT:
            raise CameraError("Image noire : la caméra est sans doute utilisée par une autre application")
        image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=cv2.cvtColor(frame, cv2.COLOR_BGR2RGB),
        )
        # Le mode VIDEO exige des horodatages strictement croissants.
        now = time.monotonic()
        ts = max(int((now - self._t0) * 1000), self._last_ts + 1)
        self._last_ts = ts
        result = self.landmarker.detect_for_video(image, ts)
        if not result.facial_transformation_matrixes:
            self._filter.reset()
            return None

        m = result.facial_transformation_matrixes[0]
        # La 3e colonne de la rotation est la direction vers laquelle le visage
        # pointe ; la 4e colonne est la position de la tête.
        fx, fy, fz = m[0][2], m[1][2], m[2][2]
        raw = (
            math.degrees(math.atan2(fx, fz)),
            math.degrees(math.asin(max(-1.0, min(1.0, -fy)))),
            *_eye_offsets(result.face_landmarks[0]),
            m[0][3], m[1][3], m[2][3],
        )
        return tuple(float(x) for x in self._filter(raw, now))

    def close(self):
        self.cap.release()
        self.landmarker.close()

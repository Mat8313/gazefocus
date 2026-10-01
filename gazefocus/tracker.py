"""Webcam -> orientation de la tête et position des iris, via MediaPipe."""
import math
import time
import urllib.request

import cv2
import mediapipe as mp

from .config import DATA_DIR

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
MODEL_PATH = DATA_DIR / "face_landmarker.task"

# (coin gauche, coin droit, centre de l'iris) de chaque œil, dans l'image.
EYES = ((33, 133, 468), (362, 263, 473))
BLACK_FRAMES_LIMIT = 30


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


def _eye_offset(landmarks) -> float:
    """Décalage horizontal moyen des iris dans les yeux : 0 = centré."""
    total = 0.0
    for left, right, iris in EYES:
        width = landmarks[right].x - landmarks[left].x
        if abs(width) < 1e-6:
            return 0.0
        total += (landmarks[iris].x - landmarks[left].x) / width - 0.5
    return total / len(EYES)


class HeadTracker:
    """Lit la caméra et renvoie une pose lissée. Aucune image n'est sauvegardée."""

    def __init__(self, camera: int = 0, smoothing: float = 0.4):
        self.camera = camera
        self.cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise CameraError(f"Impossible d'ouvrir la caméra {camera}")
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

        vision = mp.tasks.vision
        options = vision.FaceLandmarkerOptions(
            base_options=mp.tasks.BaseOptions(model_asset_path=str(ensure_model())),
            running_mode=vision.RunningMode.VIDEO,
            num_faces=1,
            output_facial_transformation_matrixes=True,
        )
        self.landmarker = vision.FaceLandmarker.create_from_options(options)
        self.smoothing = smoothing
        self.pose = None
        self._t0 = time.monotonic()
        self._last_ts = -1
        self._black = 0

    def read(self):
        """Renvoie (yaw, pitch, décalage des yeux), ou None si aucun visage.

        yaw et pitch sont en degrés. Lève CameraError si la caméra ne répond plus.
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
        ts = max(int((time.monotonic() - self._t0) * 1000), self._last_ts + 1)
        self._last_ts = ts
        result = self.landmarker.detect_for_video(image, ts)
        if not result.facial_transformation_matrixes:
            self.pose = None
            return None

        m = result.facial_transformation_matrixes[0]
        # La 3e colonne de la rotation est la direction vers laquelle le visage pointe.
        fx, fy, fz = m[0][2], m[1][2], m[2][2]
        raw = (
            math.degrees(math.atan2(fx, fz)),
            math.degrees(math.asin(max(-1.0, min(1.0, -fy)))),
            _eye_offset(result.face_landmarks[0]),
        )
        if self.pose is None:
            self.pose = raw
        else:
            a = self.smoothing
            self.pose = tuple(a * new + (1 - a) * old for new, old in zip(raw, self.pose))
        return self.pose

    def close(self):
        self.cap.release()
        self.landmarker.close()

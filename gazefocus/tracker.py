"""Webcam -> orientation de la tête (yaw, pitch) en degrés, via MediaPipe."""
import math
import os
import time
import urllib.request
from pathlib import Path

import cv2
import mediapipe as mp

MODEL_URL = (
    "https://storage.googleapis.com/mediapipe-models/face_landmarker/"
    "face_landmarker/float16/1/face_landmarker.task"
)
DATA_DIR = Path(os.environ.get("APPDATA", Path.home())) / "gazefocus"
MODEL_PATH = DATA_DIR / "face_landmarker.task"


def ensure_model() -> Path:
    """Télécharge le modèle une seule fois ; ensuite tout tourne hors ligne."""
    if not MODEL_PATH.exists():
        DATA_DIR.mkdir(parents=True, exist_ok=True)
        print(f"Téléchargement du modèle de visage (une seule fois) -> {MODEL_PATH}")
        tmp = MODEL_PATH.with_suffix(".part")
        urllib.request.urlretrieve(MODEL_URL, tmp)
        tmp.replace(MODEL_PATH)
    return MODEL_PATH


class HeadTracker:
    """Lit la caméra et renvoie une pose lissée. Aucune image n'est sauvegardée."""

    def __init__(self, camera: int = 0, smoothing: float = 0.4):
        self.cap = cv2.VideoCapture(camera, cv2.CAP_DSHOW)
        if not self.cap.isOpened():
            raise RuntimeError(f"Impossible d'ouvrir la caméra {camera}")
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
        self.frame = None
        self._t0 = time.monotonic()
        self._last_ts = -1

    def read(self):
        """Renvoie (yaw, pitch) en degrés, ou None si aucun visage n'est visible."""
        ok, frame = self.cap.read()
        if not ok:
            return None
        self.frame = frame
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
        )
        if self.pose is None:
            self.pose = raw
        else:
            a = self.smoothing
            self.pose = (
                a * raw[0] + (1 - a) * self.pose[0],
                a * raw[1] + (1 - a) * self.pose[1],
            )
        return self.pose

    def close(self):
        self.cap.release()
        self.landmarker.close()

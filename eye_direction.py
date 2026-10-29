import os
import urllib.request

import cv2
import numpy as np

import settings as cfg


class IrisGazeAnalyzer:
    def __init__(self):
        self.enabled = False
        self.landmarker = None
        if not cfg.GAZE_ENABLED:
            return
        try:
            import mediapipe as mp
            from mediapipe.tasks import python as mp_python
            from mediapipe.tasks.python import vision
            self._mp = mp
            self._ensure_model()
            options = vision.FaceLandmarkerOptions(
                base_options=mp_python.BaseOptions(model_asset_path=str(cfg.GAZE_MODEL_PATH)),
                running_mode=vision.RunningMode.IMAGE,
                num_faces=1,
                min_face_detection_confidence=0.3,
                min_face_presence_confidence=0.3,
            )
            self.landmarker = vision.FaceLandmarker.create_from_options(options)
            self.enabled = True
        except Exception as e:
            print("Gaze estimation disabled:", e)

    @staticmethod
    def _ensure_model():
        path = cfg.GAZE_MODEL_PATH
        if path.exists() and path.stat().st_size > 0:
            return
        print("Downloading face landmark model (one time)...")
        tmp = str(path) + ".part"
        urllib.request.urlretrieve(cfg.GAZE_MODEL_URL, tmp)
        os.replace(tmp, str(path))

    @staticmethod
    def _crop(frame, person):
        kp = person["kp"]
        if kp is None:
            return None
        pts = [(float(kp[i][0]), float(kp[i][1])) for i in range(5) if kp[i][2] >= 0.3]
        if len(pts) < 3:
            return None
        xs = [p[0] for p in pts]
        ys = [p[1] for p in pts]
        cx, cy = sum(xs) / len(xs), sum(ys) / len(ys)
        spread = max(max(xs) - min(xs), max(ys) - min(ys))
        size = max(spread * 2.4, 24.0)
        h, w = frame.shape[:2]
        x1, y1 = int(max(cx - size / 2, 0)), int(max(cy - size / 2, 0))
        x2, y2 = int(min(cx + size / 2, w)), int(min(cy + size / 2, h))
        if x2 - x1 < 24 or y2 - y1 < 24:
            return None
        crop = frame[y1:y2, x1:x2]
        return cv2.resize(crop, (256, 256), interpolation=cv2.INTER_CUBIC)

    @staticmethod
    def _eye_offset(lm, iris, left_corner, right_corner):
        xl, xr = lm[left_corner].x, lm[right_corner].x
        width = abs(xr - xl)
        if width < 0.03:
            return None
        return (lm[iris].x - (xl + xr) / 2.0) / width

    def estimate(self, frame, person):
        if not self.enabled:
            return None
        crop = self._crop(frame, person)
        if crop is None:
            return None
        rgb = np.ascontiguousarray(cv2.cvtColor(crop, cv2.COLOR_BGR2RGB))
        img = self._mp.Image(image_format=self._mp.ImageFormat.SRGB, data=rgb)
        res = self.landmarker.detect(img)
        if not res.face_landmarks:
            return None
        lm = res.face_landmarks[0]
        if len(lm) < 478:
            return None
        a = self._eye_offset(lm, 468, 33, 133)
        b = self._eye_offset(lm, 473, 362, 263)
        vals = [v for v in (a, b) if v is not None]
        if not vals:
            return None
        return float(np.mean(vals))


# Backward-compatible alias
GazeEstimator = IrisGazeAnalyzer

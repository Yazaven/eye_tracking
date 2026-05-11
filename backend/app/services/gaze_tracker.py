import cv2
import mediapipe as mp
import numpy as np

_face_mesh_module = mp.solutions.face_mesh

_L_IRIS = 468
_R_IRIS = 473

_L_OUTER = 33
_L_INNER = 133
_L_TOP   = 159
_L_BOT   = 145

_R_OUTER = 263
_R_INNER = 362
_R_TOP   = 386
_R_BOT   = 374

_BLINK_EAR_THRESH = 0.15
_GAIN_X = 2.0
_GAIN_Y = 3.0


class _Kalman2D:
    _DT = 1.0 / 30.0

    def __init__(self) -> None:
        kf = cv2.KalmanFilter(4, 2)
        dt = self._DT
        kf.transitionMatrix = np.array(
            [[1, 0, dt, 0], [0, 1, 0, dt], [0, 0, 1, 0], [0, 0, 0, 1]], np.float32
        )
        kf.measurementMatrix = np.array([[1, 0, 0, 0], [0, 1, 0, 0]], np.float32)
        kf.processNoiseCov = np.eye(4, dtype=np.float32) * 5e-3
        kf.measurementNoiseCov = np.eye(2, dtype=np.float32) * 1e-2
        kf.errorCovPost = np.eye(4, dtype=np.float32)
        self._kf = kf
        self._ready = False

    def update(self, x: float, y: float) -> tuple[float, float]:
        m = np.array([[x], [y]], np.float32)
        if not self._ready:
            self._kf.statePost = np.array([[x], [y], [0.0], [0.0]], np.float32)
            self._ready = True
            return x, y
        self._kf.predict()
        s = self._kf.correct(m)
        return float(s[0]), float(s[1])


class GazeTracker:
    def __init__(self) -> None:
        self._mesh = _face_mesh_module.FaceMesh(
            max_num_faces=1,
            refine_landmarks=True,
            min_detection_confidence=0.5,
            min_tracking_confidence=0.5,
        )
        self._kalman = _Kalman2D()

    @staticmethod
    def _ear(lm, top: int, bot: int, left: int, right: int) -> float:
        v = abs(lm[bot].y - lm[top].y)
        h = abs(lm[right].x - lm[left].x) + 1e-6
        return v / h

    def process(self, frame_bytes: bytes) -> tuple[float, float] | None:
        arr = np.frombuffer(frame_bytes, np.uint8)
        frame = cv2.imdecode(arr, cv2.IMREAD_COLOR)
        if frame is None:
            return None

        results = self._mesh.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        if not results.multi_face_landmarks:
            return None

        lm = results.multi_face_landmarks[0].landmark

        # blink filter
        l_ear = self._ear(lm, _L_TOP, _L_BOT, _L_INNER, _L_OUTER)
        r_ear = self._ear(lm, _R_TOP, _R_BOT, _R_OUTER, _R_INNER)
        if (l_ear + r_ear) * 0.5 < _BLINK_EAR_THRESH:
            return None

        # eye widths (horizontal span, stable and 5-6x larger than eye height)
        l_w = max(lm[_L_OUTER].x - lm[_L_INNER].x, 1e-6)
        r_w = max(lm[_R_INNER].x - lm[_R_OUTER].x, 1e-6)

        # X: iris offset from inner canthus, normalised by eye width
        # both lx and rx increase when subject looks to their left (screen-left in mirrored feed)
        lx = (lm[_L_IRIS].x - lm[_L_INNER].x) / l_w
        rx = (lm[_R_IRIS].x - lm[_R_OUTER].x) / r_w

        # Y: iris deviation from inner-canthus level, normalised by eye WIDTH (not eye height)
        # inner canthus Y tracks head pitch, so the difference is eye-rotation only
        # using eye width as the denominator reduces noise 5-6x vs the tiny eye-height
        eye_level_y = (lm[_L_INNER].y + lm[_R_INNER].y) * 0.5
        mean_w = (l_w + r_w) * 0.5
        ly = (lm[_L_IRIS].y - eye_level_y) / mean_w
        ry = (lm[_R_IRIS].y - eye_level_y) / mean_w

        # reject only catastrophically bad detections — iris completely off-face
        if not (-0.5 <= lx <= 1.5 and -0.5 <= rx <= 1.5):
            return None
        if abs(ly) > 1.0 or abs(ry) > 1.0:
            return None

        gx = (lx + rx) * 0.5   # ~0.5 at neutral
        gy = (ly + ry) * 0.5   # ~0.0 at neutral

        # screen mapping
        # X: flip because mirrored webcam feed — gx↑ means looking left → x↓
        x = float(np.clip(0.5 + (0.5 - gx) * _GAIN_X, 0.0, 1.0))
        # Y: gy>0 means looking down → y>0.5
        y = float(np.clip(0.5 + gy * _GAIN_Y, 0.0, 1.0))

        x, y = self._kalman.update(x, y)
        return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

    def close(self) -> None:
        self._mesh.close()

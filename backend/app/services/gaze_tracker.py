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
_GAIN_Y = 3.5

# Neutral adapts fast for the first 200 frames, then drifts slowly.
# This gives a ~10 s auto-calibration on first use and handles gradual posture changes.
_NEUTRAL_ALPHA_FAST = 0.02
_NEUTRAL_ALPHA_SLOW = 0.003
_NEUTRAL_WARMUP_FRAMES = 200


class _Kalman2D:
    _DT = 1.0 / 15.0

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
        self._neutral_gx: float | None = None
        self._neutral_gy: float | None = None
        self._frame_count = 0

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

        # Euclidean eye widths — invariant to head roll unlike the raw x-distance
        l_w = max(float(np.hypot(
            lm[_L_OUTER].x - lm[_L_INNER].x,
            lm[_L_OUTER].y - lm[_L_INNER].y,
        )), 1e-6)
        r_w = max(float(np.hypot(
            lm[_R_INNER].x - lm[_R_OUTER].x,
            lm[_R_INNER].y - lm[_R_OUTER].y,
        )), 1e-6)
        mean_w = (l_w + r_w) * 0.5

        # Reject frames where the face is too far / too small to be reliable
        if mean_w < 0.02:
            return None

        # Head roll from the left eye horizontal axis (outer.x > inner.x in mirrored frame)
        roll = float(np.arctan2(
            lm[_L_OUTER].y - lm[_L_INNER].y,
            lm[_L_OUTER].x - lm[_L_INNER].x,
        ))
        cos_r = float(np.cos(-roll))
        sin_r = float(np.sin(-roll))

        def unroll(dx: float, dy: float) -> tuple[float, float]:
            return cos_r * dx - sin_r * dy, sin_r * dx + cos_r * dy

        # Left iris relative to left inner canthus, un-rolled into face-level frame
        lx_v, ly_v = unroll(
            lm[_L_IRIS].x - lm[_L_INNER].x,
            lm[_L_IRIS].y - lm[_L_INNER].y,
        )
        lx = lx_v / l_w    # ~0.5 at neutral regardless of head roll
        ly = ly_v / mean_w  # ~0.0 at neutral

        # Right iris relative to right outer (temporal) canthus — same sign convention as left
        rx_v, ry_v = unroll(
            lm[_R_IRIS].x - lm[_R_OUTER].x,
            lm[_R_IRIS].y - lm[_R_OUTER].y,
        )
        rx = rx_v / r_w
        ry = ry_v / mean_w

        # Reject only catastrophically bad detections
        if not (-0.5 <= lx <= 1.5 and -0.5 <= rx <= 1.5):
            return None
        if abs(ly) > 1.0 or abs(ry) > 1.0:
            return None

        gx = (lx + rx) * 0.5   # ~0.5 at neutral; increases when looking subject-left
        gy = (ly + ry) * 0.5   # ~0.0 at neutral; increases when looking down

        # Running neutral: fast convergence for first ~200 frames, slow drift after.
        # Handles any head position or viewing angle without explicit calibration.
        alpha = _NEUTRAL_ALPHA_FAST if self._frame_count < _NEUTRAL_WARMUP_FRAMES else _NEUTRAL_ALPHA_SLOW
        self._frame_count += 1

        if self._neutral_gx is None:
            self._neutral_gx = gx
            self._neutral_gy = gy
        else:
            self._neutral_gx += alpha * (gx - self._neutral_gx)
            self._neutral_gy += alpha * (gy - self._neutral_gy)

        # Map relative to neutral → screen coords
        # X flipped: gx↑ (looking subject-left) → x↓ (screen-left in mirrored feed)
        x = float(np.clip(0.5 - (gx - self._neutral_gx) * _GAIN_X, 0.0, 1.0))
        y = float(np.clip(0.5 + (gy - self._neutral_gy) * _GAIN_Y, 0.0, 1.0))

        x, y = self._kalman.update(x, y)
        return float(np.clip(x, 0.0, 1.0)), float(np.clip(y, 0.0, 1.0))

    def close(self) -> None:
        self._mesh.close()

from dataclasses import dataclass, field
from typing import List
import mediapipe as mp
import numpy as np
from config import (
    POSE_MIN_DETECTION_CONFIDENCE,
    POSE_MIN_TRACKING_CONFIDENCE,
    HEAD_FORWARD_THRESHOLD,
    SHOULDER_UNEVEN_THRESHOLD,
)

mp_pose = mp.solutions.pose
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

# 额外阈值（不放 config 避免过度配置）
NECK_TILT_THRESHOLD = 0.06      # 头部左右偏移（颈部侧倾）
HUNCH_THRESHOLD = 0.08          # 驼背：耳朵 Y 低于肩膀 Y 的差值
TOO_CLOSE_THRESHOLD = 0.35      # 鼻子宽度占画面比例（过近）


@dataclass
class PostureResult:
    present: bool = False
    issues: List[str] = field(default_factory=list)
    confidence: float = 0.0
    landmarks: object = None


class PostureAnalyzer:
    def __init__(self):
        self.pose = mp_pose.Pose(
            min_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE,
            model_complexity=0,
        )

    def analyze(self, rgb_frame) -> PostureResult:
        results = self.pose.process(rgb_frame)
        if not results.pose_landmarks:
            return PostureResult(present=False)

        lm = results.pose_landmarks.landmark
        issues = []
        confidences = []

        NOSE          = mp_pose.PoseLandmark.NOSE
        LEFT_EAR      = mp_pose.PoseLandmark.LEFT_EAR
        RIGHT_EAR     = mp_pose.PoseLandmark.RIGHT_EAR
        LEFT_SHOULDER = mp_pose.PoseLandmark.LEFT_SHOULDER
        RIGHT_SHOULDER= mp_pose.PoseLandmark.RIGHT_SHOULDER
        LEFT_EYE      = mp_pose.PoseLandmark.LEFT_EYE
        RIGHT_EYE     = mp_pose.PoseLandmark.RIGHT_EYE

        nose       = lm[NOSE]
        l_shoulder = lm[LEFT_SHOULDER]
        r_shoulder = lm[RIGHT_SHOULDER]
        l_ear      = lm[LEFT_EAR]
        r_ear      = lm[RIGHT_EAR]
        l_eye      = lm[LEFT_EYE]
        r_eye      = lm[RIGHT_EYE]

        # 基础可见性检查
        if min(nose.visibility, l_shoulder.visibility, r_shoulder.visibility) < 0.5:
            return PostureResult(present=True, issues=[], confidence=0.5,
                                 landmarks=results.pose_landmarks)

        shoulder_mid_x = (l_shoulder.x + r_shoulder.x) / 2
        shoulder_mid_y = (l_shoulder.y + r_shoulder.y) / 2
        shoulder_width = abs(l_shoulder.x - r_shoulder.x)

        # ── 1. 头部前倾 ────────────────────────────────────────
        # 鼻子 Y 与肩膀中点 Y 的差值（归一化，Y 向下为正）
        head_drop = nose.y - shoulder_mid_y
        if head_drop > HEAD_FORWARD_THRESHOLD:
            issues.append("head_forward")
            confidences.append(min(1.0, head_drop / (HEAD_FORWARD_THRESHOLD * 2)))

        # ── 2. 肩膀不平 ────────────────────────────────────────
        shoulder_diff = abs(l_shoulder.y - r_shoulder.y)
        if shoulder_diff > SHOULDER_UNEVEN_THRESHOLD:
            issues.append("shoulder_uneven")
            confidences.append(min(1.0, shoulder_diff / (SHOULDER_UNEVEN_THRESHOLD * 2)))

        # ── 3. 颈部侧倾（头歪向一侧）──────────────────────────
        # 鼻子 X 偏离肩膀中点 X，用肩宽归一化
        if shoulder_width > 0.01:
            neck_tilt = abs(nose.x - shoulder_mid_x) / shoulder_width
            if neck_tilt > NECK_TILT_THRESHOLD / max(shoulder_width, 0.01):
                issues.append("neck_tilt")
                confidences.append(min(1.0, neck_tilt * 2))

        # ── 4. 驼背（耳朵前移）────────────────────────────────
        # 耳朵可见时：耳朵 Y 坐标接近或低于肩膀 Y（说明头往前探）
        ear_vis = min(l_ear.visibility, r_ear.visibility)
        if ear_vis > 0.5:
            ear_mid_y = (l_ear.y + r_ear.y) / 2
            hunch = ear_mid_y - shoulder_mid_y
            if hunch > HUNCH_THRESHOLD:
                issues.append("hunch")
                confidences.append(min(1.0, hunch / (HUNCH_THRESHOLD * 2)))

        # ── 5. 距离摄像头过近 ──────────────────────────────────
        # 用双眼间距占画面宽度的比例估算距离
        eye_vis = min(l_eye.visibility, r_eye.visibility)
        if eye_vis > 0.5:
            eye_dist = abs(l_eye.x - r_eye.x)
            if eye_dist > TOO_CLOSE_THRESHOLD:
                issues.append("too_close")
                confidences.append(min(1.0, eye_dist / (TOO_CLOSE_THRESHOLD * 1.5)))

        confidence = float(np.mean(confidences)) if confidences else 0.9

        return PostureResult(
            present=True,
            issues=issues,
            confidence=confidence,
            landmarks=results.pose_landmarks,
        )

    def draw(self, bgr_frame, landmarks):
        if landmarks:
            mp_drawing.draw_landmarks(
                bgr_frame,
                landmarks,
                mp_pose.POSE_CONNECTIONS,
                landmark_drawing_spec=mp_drawing_styles.get_default_pose_landmarks_style(),
            )

    def close(self):
        self.pose.close()

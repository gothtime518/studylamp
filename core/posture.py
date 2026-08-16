from dataclasses import dataclass, field
from typing import List
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import numpy as np
# 运行时读 config.X 支持热更新；置信度仅在 __init__ 用一次，直接 import 即可。
import config
from config import (
    POSE_MIN_DETECTION_CONFIDENCE,
    POSE_MIN_TRACKING_CONFIDENCE,
)
from core.mp_models import POSE_MODEL, ensure_model

# ── Pose 关键点索引 ─────────────────────────────────────────────
# mediapipe 1.0 的 Tasks API 不再暴露 PoseLandmark 枚举，直接用标准 33 点模型的
# 固定索引（跨版本稳定）。参见 MediaPipe Pose landmark 定义。
NOSE = 0
LEFT_EYE = 2
RIGHT_EYE = 5
LEFT_EAR = 7
RIGHT_EAR = 8
LEFT_SHOULDER = 11
RIGHT_SHOULDER = 12

# 额外阈值（不放 config 避免过度配置）
NECK_TILT_THRESHOLD = 0.06      # 头部左右偏移（颈部侧倾）
HUNCH_THRESHOLD = 0.08          # 驼背：耳朵 Y 低于肩膀 Y 的差值
TOO_CLOSE_THRESHOLD = 0.35      # 鼻子宽度占画面比例（过近）


@dataclass
class PostureResult:
    present: bool = False
    issues: List[str] = field(default_factory=list)
    confidence: float = 0.0
    landmarks: object = None      # Tasks API：单人的 33 个关键点列表


class PostureAnalyzer:
    def __init__(self):
        ensure_model(POSE_MODEL)
        options = vision.PoseLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=POSE_MODEL),
            running_mode=vision.RunningMode.IMAGE,
            num_poses=1,
            min_pose_detection_confidence=POSE_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=POSE_MIN_TRACKING_CONFIDENCE,
            min_pose_presence_confidence=0.5,
        )
        self.pose = vision.PoseLandmarker.create_from_options(options)

    def analyze(self, rgb_frame) -> PostureResult:
        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.ascontiguousarray(rgb_frame),
        )
        result = self.pose.detect(mp_image)
        if not result.pose_landmarks:
            return PostureResult(present=False)

        # Tasks API 返回「每个人一组关键点」的列表；num_poses=1 只取第一个人。
        lm = result.pose_landmarks[0]
        issues = []
        confidences = []

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
                                 landmarks=lm)

        shoulder_mid_x = (l_shoulder.x + r_shoulder.x) / 2
        shoulder_mid_y = (l_shoulder.y + r_shoulder.y) / 2
        shoulder_width = abs(l_shoulder.x - r_shoulder.x)

        # ── 1. 头部前倾 ────────────────────────────────────────
        # 鼻子 Y 与肩膀中点 Y 的差值（归一化，Y 向下为正）
        head_drop = nose.y - shoulder_mid_y
        if head_drop > config.HEAD_FORWARD_THRESHOLD:
            issues.append("head_forward")
            confidences.append(min(1.0, head_drop / (config.HEAD_FORWARD_THRESHOLD * 2)))

        # ── 2. 肩膀不平 ────────────────────────────────────────
        shoulder_diff = abs(l_shoulder.y - r_shoulder.y)
        if shoulder_diff > config.SHOULDER_UNEVEN_THRESHOLD:
            issues.append("shoulder_uneven")
            confidences.append(min(1.0, shoulder_diff / (config.SHOULDER_UNEVEN_THRESHOLD * 2)))

        # ── 3. 颈部侧倾（头歪向一侧）──────────────────────────
        # 鼻子 X 偏离肩膀中点 X，用肩宽归一化后 neck_tilt 已是「相对肩宽的比例」，
        # 直接与阈值常量比较即可。（旧代码把阈值又除了一次 shoulder_width，
        # 等于二次归一化，导致判定随人离摄像头远近漂移。）
        if shoulder_width > 0.01:
            neck_tilt = abs(nose.x - shoulder_mid_x) / shoulder_width
            if neck_tilt > NECK_TILT_THRESHOLD:
                issues.append("neck_tilt")
                confidences.append(min(1.0, neck_tilt / (NECK_TILT_THRESHOLD * 2)))

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
            landmarks=lm,
        )

    def draw(self, bgr_frame, landmarks):
        # Tasks API 无内置绘制工具，用 cv2 画关键点（预览用；树莓派无头运行不调用）。
        if not landmarks:
            return
        h, w = bgr_frame.shape[:2]
        for p in landmarks:
            cv2.circle(bgr_frame, (int(p.x * w), int(p.y * h)), 3, (0, 255, 0), -1)

    def close(self):
        self.pose.close()

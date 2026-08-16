from dataclasses import dataclass
from typing import Literal
import os
import cv2
import mediapipe as mp
from mediapipe.tasks import python as mp_python
from mediapipe.tasks.python import vision
import numpy as np
from config import (
    HANDS_MIN_DETECTION_CONFIDENCE,
    HANDS_MIN_TRACKING_CONFIDENCE,
    PHONE_HAND_Y_THRESHOLD,
)
from core.mp_models import HAND_MODEL, ensure_model

ActivityState = Literal["studying", "using_phone", "idle", "absent"]

# 手部关键点索引（Tasks API 不再暴露 HandLandmark 枚举，用标准 21 点模型固定索引）
WRIST = 0

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "dataset", "activity_model.pkl"
)


@dataclass
class ActivityResult:
    state: ActivityState = "absent"
    confidence: float = 0.0
    hand_landmarks: list = None      # Tasks API：list[list[landmark]]，每只手 21 个点


class ActivityClassifier:
    def __init__(self):
        ensure_model(HAND_MODEL)
        options = vision.HandLandmarkerOptions(
            base_options=mp_python.BaseOptions(model_asset_path=HAND_MODEL),
            running_mode=vision.RunningMode.IMAGE,
            num_hands=2,
            min_hand_detection_confidence=HANDS_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=HANDS_MIN_TRACKING_CONFIDENCE,
            min_hand_presence_confidence=0.5,
        )
        self.hands = vision.HandLandmarker.create_from_options(options)
        self._model = None
        self._scaler = None
        self._label_inv = None
        self._try_load_model()

    def _try_load_model(self):
        if not os.path.exists(MODEL_PATH):
            return
        try:
            import pickle
            with open(MODEL_PATH, "rb") as f:
                data = pickle.load(f)
            self._model = data["clf"]
            self._scaler = data["scaler"]
            self._label_inv = data["label_inv"]
            print(f"[activity] 已加载训练模型 {MODEL_PATH}")
        except Exception as e:
            print(f"[activity] 模型加载失败，使用规则分类: {e}")

    def classify(self, rgb_frame, person_present: bool) -> ActivityResult:
        if not person_present:
            return ActivityResult(state="absent", confidence=1.0, hand_landmarks=[])

        mp_image = mp.Image(
            image_format=mp.ImageFormat.SRGB,
            data=np.ascontiguousarray(rgb_frame),
        )
        result = self.hands.detect(mp_image)
        # Tasks API：result.hand_landmarks 是 list[list[landmark]]（每只手一组 21 点）
        hand_lms = result.hand_landmarks or []

        # 如果有训练好的模型，优先使用
        if self._model is not None:
            return self._classify_with_model(hand_lms)

        return self._classify_with_rules(hand_lms)

    def _classify_with_model(self, hand_lms) -> ActivityResult:
        if not hand_lms:
            feat = np.zeros(63)
        else:
            lm = hand_lms[0]      # 第一只手的 21 个关键点列表
            feat = np.array([[p.x, p.y, p.z] for p in lm]).flatten()

        feat_scaled = self._scaler.transform([feat])
        pred = self._model.predict(feat_scaled)[0]
        proba = self._model.predict_proba(feat_scaled)[0]
        state = self._label_inv.get(pred, "idle")
        confidence = float(proba[pred])
        return ActivityResult(state=state, confidence=confidence, hand_landmarks=hand_lms)

    def _classify_with_rules(self, hand_lms) -> ActivityResult:
        if not hand_lms:
            return ActivityResult(state="idle", confidence=0.75, hand_landmarks=[])

        wrist_ys = [h[WRIST].y for h in hand_lms]
        min_wrist_y = min(wrist_ys)
        num_hands = len(hand_lms)

        if min_wrist_y < PHONE_HAND_Y_THRESHOLD:
            confidence = min(1.0, (PHONE_HAND_Y_THRESHOLD - min_wrist_y) / PHONE_HAND_Y_THRESHOLD + 0.6)
            return ActivityResult(state="using_phone", confidence=confidence, hand_landmarks=hand_lms)

        confidence = 0.8 if num_hands == 1 else 0.9
        return ActivityResult(state="studying", confidence=confidence, hand_landmarks=hand_lms)

    def draw(self, bgr_frame, hand_landmarks):
        # Tasks API 无内置绘制工具，用 cv2 画关键点（预览用；树莓派无头运行不调用）。
        if not hand_landmarks:
            return
        h, w = bgr_frame.shape[:2]
        for hand_lm in hand_landmarks:
            for p in hand_lm:
                cv2.circle(bgr_frame, (int(p.x * w), int(p.y * h)), 3, (255, 0, 0), -1)

    def close(self):
        self.hands.close()

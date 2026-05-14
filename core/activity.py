from dataclasses import dataclass
from typing import Literal
import os
import mediapipe as mp
import numpy as np
from config import (
    HANDS_MIN_DETECTION_CONFIDENCE,
    HANDS_MIN_TRACKING_CONFIDENCE,
    PHONE_HAND_Y_THRESHOLD,
)

mp_hands = mp.solutions.hands
mp_drawing = mp.solutions.drawing_utils
mp_drawing_styles = mp.solutions.drawing_styles

ActivityState = Literal["studying", "using_phone", "idle", "absent"]

MODEL_PATH = os.path.join(
    os.path.dirname(os.path.dirname(__file__)), "dataset", "activity_model.pkl"
)


@dataclass
class ActivityResult:
    state: ActivityState = "absent"
    confidence: float = 0.0
    hand_landmarks: list = None


class ActivityClassifier:
    def __init__(self):
        self.hands = mp_hands.Hands(
            max_num_hands=2,
            min_detection_confidence=HANDS_MIN_DETECTION_CONFIDENCE,
            min_tracking_confidence=HANDS_MIN_TRACKING_CONFIDENCE,
            model_complexity=0,
        )
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

        results = self.hands.process(rgb_frame)

        # 如果有训练好的模型，优先使用
        if self._model is not None:
            return self._classify_with_model(results)

        return self._classify_with_rules(results)

    def _classify_with_model(self, results) -> ActivityResult:
        hand_lms = results.multi_hand_landmarks or []
        if not hand_lms:
            feat = np.zeros(63)
        else:
            lm = hand_lms[0].landmark
            feat = np.array([[p.x, p.y, p.z] for p in lm]).flatten()

        feat_scaled = self._scaler.transform([feat])
        pred = self._model.predict(feat_scaled)[0]
        proba = self._model.predict_proba(feat_scaled)[0]
        state = self._label_inv.get(pred, "idle")
        confidence = float(proba[pred])
        return ActivityResult(state=state, confidence=confidence, hand_landmarks=hand_lms or [])

    def _classify_with_rules(self, results) -> ActivityResult:
        if not results.multi_hand_landmarks:
            return ActivityResult(state="idle", confidence=0.75, hand_landmarks=[])

        hand_lms = results.multi_hand_landmarks
        wrist_ys = [h.landmark[mp_hands.HandLandmark.WRIST].y for h in hand_lms]
        min_wrist_y = min(wrist_ys)
        num_hands = len(hand_lms)

        if min_wrist_y < PHONE_HAND_Y_THRESHOLD:
            confidence = min(1.0, (PHONE_HAND_Y_THRESHOLD - min_wrist_y) / PHONE_HAND_Y_THRESHOLD + 0.6)
            return ActivityResult(state="using_phone", confidence=confidence, hand_landmarks=hand_lms)

        confidence = 0.8 if num_hands == 1 else 0.9
        return ActivityResult(state="studying", confidence=confidence, hand_landmarks=hand_lms)

    def draw(self, bgr_frame, hand_landmarks):
        if hand_landmarks:
            for hand_lm in hand_landmarks:
                mp_drawing.draw_landmarks(
                    bgr_frame,
                    hand_lm,
                    mp_hands.HAND_CONNECTIONS,
                    mp_drawing_styles.get_default_hand_landmarks_style(),
                    mp_drawing_styles.get_default_hand_connections_style(),
                )

    def close(self):
        self.hands.close()

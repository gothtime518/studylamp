import threading
import time
import os
import cv2
import numpy as np
from core.posture import PostureAnalyzer, PostureResult
from core.activity import ActivityClassifier, ActivityResult
from core.events import write_event
from config import (
    CAMERA_INDEX,
    FRAME_WIDTH,
    FRAME_HEIGHT,
    SAMPLE_INTERVAL_ACTIVE,
    SAMPLE_INTERVAL_IDLE,
    CONFIRM_COUNT,
    DATA_DIR,
)


def _push_state_bg(state: str):
    """后台推送实时状态，导入延迟避免循环依赖"""
    try:
        from core.sync import push_realtime_state
        push_realtime_state(state)
    except Exception:
        pass


class CameraLoop:
    def __init__(self, on_state_change=None):
        """
        on_state_change: callable(state_str) — 状态变化时回调，用于更新菜单栏图标
        state_str: "studying" | "warning" | "distracted" | "absent"
        """
        self.on_state_change = on_state_change
        self._stop_event = threading.Event()
        self._thread = None

        self._posture = None
        self._activity = None

        # 最新帧（供预览窗口读取）
        self._frame_lock = threading.Lock()
        self._latest_frame = None          # BGR, with overlays
        self._latest_posture: PostureResult = PostureResult()
        self._latest_activity: ActivityResult = ActivityResult()

        # 连续异常计数（3 次确认机制）
        self._posture_bad_count = 0
        self._phone_count = 0
        self._last_activity_state = "absent"

        self._session_active = False

        # 作业拍照：activity 切换到 studying 时触发一次
        self._homework_callback = None   # callable(image_path) — 外部注册
        self._last_homework_capture = 0  # 防止频繁触发，最少间隔 120s

    # ── 公开接口 ──────────────────────────────────────────────

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._session_active:
            write_event("session_end", {})
            self._session_active = False
        if self._posture:
            self._posture.close()
        if self._activity:
            self._activity.close()
        self._posture = None
        self._activity = None

    def register_homework_callback(self, callback):
        """注册作业拍照回调，activity 切换到 studying 时触发"""
        self._homework_callback = callback

    def capture_homework_frame(self) -> str | None:
        """手动触发拍照，保存到本地，返回图片路径"""
        frame = self.get_latest_frame()
        if frame is None:
            return None
        os.makedirs(DATA_DIR, exist_ok=True)
        ts = time.strftime("%Y%m%d_%H%M%S")
        path = os.path.join(DATA_DIR, f"homework_{ts}.jpg")
        cv2.imwrite(path, frame)
        return path

    def get_latest_frame(self):
        with self._frame_lock:
            return self._latest_frame.copy() if self._latest_frame is not None else None

    def get_current_state(self) -> str:
        act = self._latest_activity.state
        issues = self._latest_posture.issues
        if act == "absent":
            return "absent"
        if act == "using_phone":
            return "distracted"
        if issues:
            return "warning"
        return "studying"

    # ── 内部循环 ──────────────────────────────────────────────

    def _loop(self):
        # 在子线程里初始化 MediaPipe，避免阻塞 rumps 主线程
        self._posture = PostureAnalyzer()
        self._activity = ActivityClassifier()

        # 启动时清理过期图片
        from core.cleanup import cleanup_old_images
        cleanup_old_images()

        cap = cv2.VideoCapture(CAMERA_INDEX)
        cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
        cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

        if not cap.isOpened():
            return

        last_sample_time = 0

        while not self._stop_event.is_set():
            ret, frame = cap.read()
            if not ret:
                time.sleep(0.1)
                continue

            now = time.time()
            person_present = self._latest_posture.present
            interval = SAMPLE_INTERVAL_ACTIVE if person_present else SAMPLE_INTERVAL_IDLE

            if now - last_sample_time >= interval:
                last_sample_time = now
                self._analyze(frame)

            # 叠加骨骼线和状态文字
            annotated = self._annotate(frame.copy())
            with self._frame_lock:
                self._latest_frame = annotated

            time.sleep(0.03)  # ~30fps 预览刷新

        cap.release()

    def _analyze(self, frame):
        rgb = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)

        posture = self._posture.analyze(rgb)
        activity = self._activity.classify(rgb, posture.present)

        self._latest_posture = posture
        self._latest_activity = activity

        # session 管理
        if posture.present and not self._session_active:
            self._session_active = True
            write_event("session_start", {})
        elif not posture.present and self._session_active:
            self._session_active = False
            write_event("session_end", {})

        # 活动状态变化事件
        if activity.state != self._last_activity_state:
            if self._last_activity_state != "absent":
                write_event("activity_change", {
                    "from": self._last_activity_state,
                    "to": activity.state,
                    "confidence": round(activity.confidence, 2),
                })
            # 切换到 studying 时触发作业拍照（间隔 120s 防抖）
            if (activity.state == "studying"
                    and self._homework_callback
                    and time.time() - self._last_homework_capture > 120):
                path = self.capture_homework_frame()
                if path:
                    self._last_homework_capture = time.time()
                    threading.Thread(
                        target=self._homework_callback,
                        args=(path,),
                        daemon=True,
                    ).start()
            self._last_activity_state = activity.state

        # 坐姿异常（3 次确认）
        if posture.issues:
            self._posture_bad_count += 1
            if self._posture_bad_count >= CONFIRM_COUNT:
                write_event("posture_bad", {
                    "issues": posture.issues,
                    "confidence": round(posture.confidence, 2),
                })
                self._posture_bad_count = 0
        else:
            self._posture_bad_count = max(0, self._posture_bad_count - 1)

        # 玩手机（3 次确认）
        if activity.state == "using_phone":
            self._phone_count += 1
            if self._phone_count >= CONFIRM_COUNT:
                write_event("phone_detected", {
                    "confidence": round(activity.confidence, 2),
                })
                self._phone_count = 0
        else:
            self._phone_count = max(0, self._phone_count - 1)

        # 回调更新菜单栏 + 推送实时状态到服务器
        current_state = self.get_current_state()
        if self.on_state_change:
            self.on_state_change(current_state)
        # 后台推送，不阻塞分析循环
        threading.Thread(
            target=_push_state_bg,
            args=(current_state,),
            daemon=True,
        ).start()

    def _annotate(self, bgr_frame) -> np.ndarray:
        self._posture.draw(bgr_frame, self._latest_posture.landmarks)
        self._activity.draw(bgr_frame, self._latest_activity.hand_landmarks)

        state = self.get_current_state()
        color_map = {
            "studying":   (0, 200, 80),
            "warning":    (0, 180, 255),
            "distracted": (0, 60, 220),
            "absent":     (160, 160, 160),
        }
        label_map = {
            "studying":   "Studying",
            "warning":    "Posture Warning",
            "distracted": "Distracted",
            "absent":     "No one detected",
        }
        color = color_map.get(state, (200, 200, 200))
        label = label_map.get(state, state)

        cv2.putText(bgr_frame, label, (12, 32),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.9, color, 2, cv2.LINE_AA)

        if self._latest_posture.issues:
            issues_str = " | ".join(self._latest_posture.issues)
            cv2.putText(bgr_frame, issues_str, (12, 62),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 180, 255), 1, cv2.LINE_AA)

        return bgr_frame

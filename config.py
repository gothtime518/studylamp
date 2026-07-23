import os
import sys

# 采样间隔（秒）
SAMPLE_INTERVAL_ACTIVE = 5      # 有人在场
SAMPLE_INTERVAL_IDLE = 60       # 无人在场
CONFIRM_COUNT = 3               # 连续 N 次确认才写事件（避免误报）

# 坐姿阈值
HEAD_FORWARD_THRESHOLD = 0.12   # 鼻子相对肩膀中点的前倾比例
SHOULDER_UNEVEN_THRESHOLD = 0.04  # 左右肩高度差比例

# 手部活动阈值
PHONE_HAND_Y_THRESHOLD = 0.45   # 手腕 Y 坐标高于此值视为举手（玩手机）

# 数据存储
# 优先用环境变量 STUDYLAMP_DATA_DIR；否则按平台选择默认目录：
#   macOS → ~/Library/Application Support/StudyLamp
#   Linux/树莓派 → ~/.local/share/studylamp（遵循 XDG_DATA_HOME）
#   其他 → ~/.studylamp
def _default_data_dir() -> str:
    env = os.environ.get("STUDYLAMP_DATA_DIR")
    if env:
        return os.path.expanduser(env)
    if sys.platform == "darwin":
        return os.path.expanduser("~/Library/Application Support/StudyLamp")
    if sys.platform.startswith("linux"):
        base = os.environ.get("XDG_DATA_HOME") or os.path.expanduser("~/.local/share")
        return os.path.join(base, "studylamp")
    return os.path.expanduser("~/.studylamp")


DATA_DIR = _default_data_dir()
EVENTS_FILE = os.path.join(DATA_DIR, "events.jsonl")

# 摄像头
CAMERA_INDEX = 0
FRAME_WIDTH = 640
FRAME_HEIGHT = 480

# MediaPipe 置信度
POSE_MIN_DETECTION_CONFIDENCE = 0.6
POSE_MIN_TRACKING_CONFIDENCE = 0.6
HANDS_MIN_DETECTION_CONFIDENCE = 0.6
HANDS_MIN_TRACKING_CONFIDENCE = 0.6

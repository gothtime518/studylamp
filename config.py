import os

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
DATA_DIR = os.path.expanduser("~/Library/Application Support/StudyLamp")
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

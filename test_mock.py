"""
模拟测试框架 — 不需要摄像头，验证事件系统和核心逻辑
运行：python3 test_mock.py
"""
import sys
import os
import tempfile
import json
import numpy as np

sys.path.insert(0, os.path.dirname(__file__))

# 用临时目录隔离测试数据
_tmp_dir = tempfile.mkdtemp()
import config
config.DATA_DIR = _tmp_dir
config.EVENTS_FILE = os.path.join(_tmp_dir, "events.jsonl")

from core.events import write_event, read_today_events, today_summary
from core.posture import PostureAnalyzer, PostureResult
from core.activity import ActivityClassifier, ActivityResult


PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
_results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}" + (f"  ({detail})" if detail else ""))
    _results.append(condition)


# ── 1. 事件系统 ────────────────────────────────────────────────

print("\n[1] 事件系统")

write_event("session_start", {})
write_event("posture_bad", {"issues": ["head_forward"], "confidence": 0.88})
write_event("activity_change", {"from": "studying", "to": "using_phone", "confidence": 0.91})
write_event("phone_detected", {"confidence": 0.91})
write_event("session_end", {})

events = read_today_events()
check("写入 5 条事件", len(events) == 5, f"got {len(events)}")
check("事件类型正确", events[1]["type"] == "posture_bad")
check("synced 默认 False", events[0]["synced"] is False)
check("timestamp 格式正确", "T" in events[0]["timestamp"])

summary = today_summary()
check("posture_bad_count == 1", summary["posture_bad_count"] == 1, str(summary))
check("phone_count == 1", summary["phone_count"] == 1, str(summary))

# ── 2. 坐姿分析（黑盒：空白帧 → absent）─────────────────────

print("\n[2] 坐姿分析（空白帧）")

analyzer = PostureAnalyzer()
blank = np.zeros((480, 640, 3), dtype=np.uint8)
result = analyzer.analyze(blank)
check("空白帧 present=False", result.present is False)
check("空白帧 issues 为空", result.issues == [])
analyzer.close()

# ── 3. 活动分类（黑盒：空白帧 + person_present=False → absent）

print("\n[3] 活动分类（空白帧）")

classifier = ActivityClassifier()
blank = np.zeros((480, 640, 3), dtype=np.uint8)
result = classifier.classify(blank, person_present=False)
check("无人时 state=absent", result.state == "absent")
check("无人时 confidence=1.0", result.confidence == 1.0)

result2 = classifier.classify(blank, person_present=True)
check("有人无手时 state=idle", result2.state == "idle")
classifier.close()

# ── 4. PostureResult / ActivityResult 数据结构 ────────────────

print("\n[4] 数据结构")

pr = PostureResult(present=True, issues=["head_forward", "shoulder_uneven"], confidence=0.85)
check("PostureResult issues 列表", isinstance(pr.issues, list))
check("PostureResult confidence 范围", 0 <= pr.confidence <= 1)

ar = ActivityResult(state="studying", confidence=0.9)
check("ActivityResult state 正确", ar.state == "studying")
check("ActivityResult hand_landmarks 默认 None", ar.hand_landmarks is None)

# ── 5a. 坐姿问题类型覆盖 ──────────────────────────────────────

print("\n[5] 坐姿问题类型")

all_issue_types = {"head_forward", "shoulder_uneven", "neck_tilt", "hunch", "too_close"}
pr2 = PostureResult(present=True, issues=list(all_issue_types), confidence=0.9)
check("支持所有坐姿问题类型", set(pr2.issues) == all_issue_types)
check("issues 均为字符串", all(isinstance(i, str) for i in pr2.issues))

# ── 6. 事件 JSON 格式验证 ─────────────────────────────────────

print("\n[6] 事件 JSON 格式")

with open(config.EVENTS_FILE, "r") as f:
    lines = [l.strip() for l in f if l.strip()]

check("每行都是合法 JSON", all(json.loads(l) for l in lines))
required_keys = {"type", "timestamp", "details", "synced"}
check("每条事件包含必要字段", all(required_keys <= set(json.loads(l).keys()) for l in lines))

# ── 汇总 ──────────────────────────────────────────────────────
total = len(_results)
passed = sum(_results)
print(f"\n{'='*40}")
print(f"结果：{passed}/{total} 通过")
if passed == total:
    print("✅ 全部通过")
else:
    print(f"❌ {total - passed} 项失败")
    sys.exit(1)

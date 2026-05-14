"""
积分系统端到端测试
运行：python3 test_points.py
"""
import sys
import os
import json
import time
import tempfile
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

_tmp_dir = tempfile.mkdtemp()
os.environ["STUDYLAMP_DB"] = os.path.join(_tmp_dir, "test_points.db")
os.environ["STUDYLAMP_SERVER"] = "http://127.0.0.1:18766"
os.environ["STUDYLAMP_DEVICE_ID"] = "points-test-001"

import config
config.DATA_DIR = _tmp_dir
config.EVENTS_FILE = os.path.join(_tmp_dir, "events.jsonl")

from core.events import write_event
from core.sync import CloudSync
from server.points import calc_daily_points, calc_badges

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
_results = []


def check(name, condition, detail=""):
    status = PASS if condition else FAIL
    print(f"  {status} {name}" + (f"  ({detail})" if detail else ""))
    _results.append(condition)


# ── 启动测试服务器 ─────────────────────────────────────────────

def start_server():
    import uvicorn
    from server.app import app
    uvicorn.run(app, host="127.0.0.1", port=18766, log_level="error")


server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

for _ in range(20):
    try:
        urllib.request.urlopen("http://127.0.0.1:18766/health", timeout=1)
        break
    except Exception:
        time.sleep(0.3)
else:
    print("❌ 服务器启动失败")
    sys.exit(1)

print("服务器已就绪\n")


# ── 1. 积分计算规则 ────────────────────────────────────────────

print("[1] 积分计算规则")

# 60 分钟学习 = 2 * 10 = 20 分
ledger = calc_daily_points(study_minutes=60, posture_bad_count=0, phone_count=0, streak=1)
total = sum(i["points"] for i in ledger)
check("60分钟学习得 20 分", total >= 20, f"got {total}")
check("坐姿良好额外 5 分", any(i["reason"] == "good_posture" for i in ledger))
check("不玩手机额外 5 分", any(i["reason"] == "no_phone" for i in ledger))

# 连续 3 天额外 20 分
ledger2 = calc_daily_points(study_minutes=30, posture_bad_count=0, phone_count=0, streak=3)
check("连续 3 天额外 20 分", any(i["reason"] == "streak" for i in ledger2))

# 有坐姿问题不得坐姿奖励
ledger3 = calc_daily_points(study_minutes=60, posture_bad_count=2, phone_count=0, streak=1)
check("有坐姿问题不得坐姿奖励", not any(i["reason"] == "good_posture" for i in ledger3))


# ── 2. 徽章系统 ────────────────────────────────────────────────

print("\n[2] 徽章系统")

badges = calc_badges({"study_minutes": 0, "posture_bad_count": 0, "phone_count": 0,
                      "streak": 0, "total_days": 1})
check("total_days=1 解锁初次启动徽章", any(b["id"] == "first_session" for b in badges))

badges2 = calc_badges({"study_minutes": 65, "posture_bad_count": 0, "phone_count": 0,
                       "streak": 0, "total_days": 1})
check("study_minutes=65 解锁专注达人", any(b["id"] == "focus_60" for b in badges2))
check("坐姿 0 次解锁坐姿标准", any(b["id"] == "posture_perfect" for b in badges2))

badges3 = calc_badges({"study_minutes": 30, "posture_bad_count": 0, "phone_count": 0,
                       "streak": 7, "total_days": 7})
check("streak=7 解锁一周坚持", any(b["id"] == "streak_7" for b in badges3))


# ── 3. 积分 API 端到端 ─────────────────────────────────────────

print("\n[3] 积分 API")

# 写入学习事件
today = time.strftime("%Y-%m-%d")
write_event("session_start", {})
time.sleep(0.01)
write_event("session_end", {})

sync = CloudSync()
sync.sync_now()

# 调用积分计算
url = f"http://127.0.0.1:18766/api/v1/points/calc?device_id=points-test-001&date={today}"
req = urllib.request.Request(url, method="POST")
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
check("POST /points/calc 返回 200", resp.status == 200)
check("返回 today_points 字段", "today_points" in data, str(data))
check("返回 badges 字段", "badges" in data)
check("返回 streak 字段", "streak" in data)

# 积分汇总
url2 = f"http://127.0.0.1:18766/api/v1/points/summary?device_id=points-test-001"
resp2 = urllib.request.urlopen(url2)
summary = json.loads(resp2.read())
check("GET /points/summary 返回 200", resp2.status == 200)
check("total_points >= 0", summary.get("total_points", -1) >= 0)
check("active_days >= 1", summary.get("active_days", 0) >= 1)


# ── 4. 多孩子 API ──────────────────────────────────────────────

print("\n[4] 多孩子 API")

payload = json.dumps({
    "parent_openid": "test-parent-001",
    "name": "小明",
    "device_id": "points-test-001",
}).encode()
req = urllib.request.Request(
    "http://127.0.0.1:18766/api/v1/children",
    data=payload,
    headers={"Content-Type": "application/json"},
    method="POST",
)
resp = urllib.request.urlopen(req)
child = json.loads(resp.read())
check("POST /children 返回 200", resp.status == 200)
check("返回 name=小明", child.get("name") == "小明")

resp2 = urllib.request.urlopen(
    "http://127.0.0.1:18766/api/v1/children?parent_openid=test-parent-001"
)
children = json.loads(resp2.read())
check("GET /children 返回列表", isinstance(children, list))
check("列表包含刚绑定的孩子", len(children) >= 1)

# 重复绑定应返回 409
try:
    urllib.request.urlopen(req)
    check("重复绑定返回 409", False, "应该抛出异常")
except urllib.error.HTTPError as e:
    check("重复绑定返回 409", e.code == 409, f"got {e.code}")


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

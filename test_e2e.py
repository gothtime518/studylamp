"""
端到端集成测试 — 启动内嵌测试服务器，验证 API + 同步模块
运行：python3 test_e2e.py
"""
import sys
import os
import json
import time
import tempfile
import threading
import urllib.request

sys.path.insert(0, os.path.dirname(__file__))

# 隔离测试数据库和事件文件
_tmp_dir = tempfile.mkdtemp()
os.environ["STUDYLAMP_DB"] = os.path.join(_tmp_dir, "test.db")
os.environ["STUDYLAMP_SERVER"] = "http://127.0.0.1:18765"
os.environ["STUDYLAMP_DEVICE_ID"] = "test-device-001"

import config
config.DATA_DIR = _tmp_dir
config.EVENTS_FILE = os.path.join(_tmp_dir, "events.jsonl")

from core.events import write_event
from core.sync import CloudSync

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
    uvicorn.run(app, host="127.0.0.1", port=18765, log_level="error")


server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

# 等待服务器就绪
for _ in range(20):
    try:
        urllib.request.urlopen("http://127.0.0.1:18765/health", timeout=1)
        break
    except Exception:
        time.sleep(0.3)
else:
    print("❌ 服务器启动失败")
    sys.exit(1)

print("服务器已就绪\n")


# ── 1. 健康检查 ────────────────────────────────────────────────

print("[1] 健康检查")
resp = urllib.request.urlopen("http://127.0.0.1:18765/health")
data = json.loads(resp.read())
check("GET /health 返回 200", resp.status == 200)
check("status == ok", data.get("status") == "ok")


# ── 2. 写本地事件 ──────────────────────────────────────────────

print("\n[2] 本地事件写入")
write_event("session_start", {})
time.sleep(0.01)
write_event("posture_bad", {"issues": ["head_forward"], "confidence": 0.88})
write_event("activity_change", {"from": "studying", "to": "using_phone", "confidence": 0.91})
write_event("session_end", {})

with open(config.EVENTS_FILE) as f:
    lines = [l.strip() for l in f if l.strip()]
check("本地写入 4 条事件", len(lines) == 4, f"got {len(lines)}")
check("全部 synced=false", all(not json.loads(l)["synced"] for l in lines))


# ── 3. 云同步 ─────────────────────────────────────────────────

print("\n[3] 云同步")
sync = CloudSync()
result = sync.sync_now()
check(f"上传 4 条事件", result["synced"] == 4, str(result))
check("failed == 0", result["failed"] == 0)

with open(config.EVENTS_FILE) as f:
    lines = [l.strip() for l in f if l.strip()]
check("本地标记 synced=true", all(json.loads(l)["synced"] for l in lines))


# ── 4. 日报 API ────────────────────────────────────────────────

print("\n[4] 日报 API")
today = time.strftime("%Y-%m-%d")
url = f"http://127.0.0.1:18765/api/v1/report/daily/{today}?device_id=test-device-001"
resp = urllib.request.urlopen(url)
report = json.loads(resp.read())
check("GET /report/daily 返回 200", resp.status == 200)
check("event_count == 4", report["event_count"] == 4, str(report))
check("posture_bad_count == 1", report["posture_bad_count"] == 1)
check("phone_count == 1", report["phone_count"] == 1)


# ── 5. 重复同步不重复上传 ──────────────────────────────────────

print("\n[5] 重复同步")
result2 = sync.sync_now()
check("无待同步事件时 synced==0", result2["synced"] == 0, str(result2))


# ── 6. 作业上传 API ────────────────────────────────────────────

print("\n[6] 作业上传")

import io

# 构造一个 1x1 白色 JPEG（最小合法图片）
def minimal_jpeg() -> bytes:
    import struct, zlib
    # 用 PNG 格式（更简单），FastAPI 只检查 Content-Type
    # 实际用一个最小 JPEG 字节序列
    return bytes([
        0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46, 0x00, 0x01,
        0x01, 0x00, 0x00, 0x01, 0x00, 0x01, 0x00, 0x00, 0xFF, 0xDB, 0x00, 0x43,
        0x00, 0x08, 0x06, 0x06, 0x07, 0x06, 0x05, 0x08, 0x07, 0x07, 0x07, 0x09,
        0x09, 0x08, 0x0A, 0x0C, 0x14, 0x0D, 0x0C, 0x0B, 0x0B, 0x0C, 0x19, 0x12,
        0x13, 0x0F, 0x14, 0x1D, 0x1A, 0x1F, 0x1E, 0x1D, 0x1A, 0x1C, 0x1C, 0x20,
        0x24, 0x2E, 0x27, 0x20, 0x22, 0x2C, 0x23, 0x1C, 0x1C, 0x28, 0x37, 0x29,
        0x2C, 0x30, 0x31, 0x34, 0x34, 0x34, 0x1F, 0x27, 0x39, 0x3D, 0x38, 0x32,
        0x3C, 0x2E, 0x33, 0x34, 0x32, 0xFF, 0xC0, 0x00, 0x0B, 0x08, 0x00, 0x01,
        0x00, 0x01, 0x01, 0x01, 0x11, 0x00, 0xFF, 0xC4, 0x00, 0x1F, 0x00, 0x00,
        0x01, 0x05, 0x01, 0x01, 0x01, 0x01, 0x01, 0x01, 0x00, 0x00, 0x00, 0x00,
        0x00, 0x00, 0x00, 0x00, 0x01, 0x02, 0x03, 0x04, 0x05, 0x06, 0x07, 0x08,
        0x09, 0x0A, 0x0B, 0xFF, 0xC4, 0x00, 0xB5, 0x10, 0x00, 0x02, 0x01, 0x03,
        0x03, 0x02, 0x04, 0x03, 0x05, 0x05, 0x04, 0x04, 0x00, 0x00, 0x01, 0x7D,
        0x01, 0x02, 0x03, 0x00, 0x04, 0x11, 0x05, 0x12, 0x21, 0x31, 0x41, 0x06,
        0x13, 0x51, 0x61, 0x07, 0x22, 0x71, 0x14, 0x32, 0x81, 0x91, 0xA1, 0x08,
        0x23, 0x42, 0xB1, 0xC1, 0x15, 0x52, 0xD1, 0xF0, 0x24, 0x33, 0x62, 0x72,
        0x82, 0x09, 0x0A, 0x16, 0x17, 0x18, 0x19, 0x1A, 0x25, 0x26, 0x27, 0x28,
        0x29, 0x2A, 0x34, 0x35, 0x36, 0x37, 0x38, 0x39, 0x3A, 0x43, 0x44, 0x45,
        0x46, 0x47, 0x48, 0x49, 0x4A, 0x53, 0x54, 0x55, 0x56, 0x57, 0x58, 0x59,
        0x5A, 0x63, 0x64, 0x65, 0x66, 0x67, 0x68, 0x69, 0x6A, 0x73, 0x74, 0x75,
        0x76, 0x77, 0x78, 0x79, 0x7A, 0x83, 0x84, 0x85, 0x86, 0x87, 0x88, 0x89,
        0x8A, 0x92, 0x93, 0x94, 0x95, 0x96, 0x97, 0x98, 0x99, 0x9A, 0xA2, 0xA3,
        0xA4, 0xA5, 0xA6, 0xA7, 0xA8, 0xA9, 0xAA, 0xB2, 0xB3, 0xB4, 0xB5, 0xB6,
        0xB7, 0xB8, 0xB9, 0xBA, 0xC2, 0xC3, 0xC4, 0xC5, 0xC6, 0xC7, 0xC8, 0xC9,
        0xCA, 0xD2, 0xD3, 0xD4, 0xD5, 0xD6, 0xD7, 0xD8, 0xD9, 0xDA, 0xE1, 0xE2,
        0xE3, 0xE4, 0xE5, 0xE6, 0xE7, 0xE8, 0xE9, 0xEA, 0xF1, 0xF2, 0xF3, 0xF4,
        0xF5, 0xF6, 0xF7, 0xF8, 0xF9, 0xFA, 0xFF, 0xDA, 0x00, 0x08, 0x01, 0x01,
        0x00, 0x00, 0x3F, 0x00, 0xFB, 0xD2, 0x8A, 0x28, 0x03, 0xFF, 0xD9,
    ])


boundary = "----TestBoundary"
img_data = minimal_jpeg()

def build_multipart(device_id, subject, ocr_text, img_bytes):
    parts = []
    def field(name, val):
        return (f"--{boundary}\r\nContent-Disposition: form-data; name=\"{name}\"\r\n\r\n{val}\r\n").encode()
    parts.append(field("device_id", device_id))
    parts.append(field("subject", subject))
    parts.append(field("ocr_text", ocr_text))
    header = (f"--{boundary}\r\nContent-Disposition: form-data; name=\"file\"; filename=\"test.jpg\"\r\nContent-Type: image/jpeg\r\n\r\n").encode()
    parts.append(header + img_bytes + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return b"".join(parts)

body = build_multipart("test-device-001", "数学", "1+1=2", img_data)
req = urllib.request.Request(
    "http://127.0.0.1:18765/api/v1/homework",
    data=body,
    headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    method="POST",
)
resp = urllib.request.urlopen(req)
hw = json.loads(resp.read())
check("POST /homework 返回 200", resp.status == 200)
check("返回 subject 字段", "subject" in hw, str(hw))
check("返回 id 字段", "id" in hw)

hw_id = hw["id"]
resp2 = urllib.request.urlopen(f"http://127.0.0.1:18765/api/v1/homework/{hw_id}/analysis")
hw_detail = json.loads(resp2.read())
check("GET /homework/{id}/analysis 返回 200", resp2.status == 200)
check("detail id 一致", hw_detail["id"] == hw_id)


# ── 7. 限流测试 ────────────────────────────────────────────────

print("\n[7] 限流（Rate Limit）")

# 快速发送 61 次，第 61 次应返回 429
hit_429 = False
for i in range(62):
    payload = json.dumps({"device_id": "rate-test-001", "events": []}).encode()
    req = urllib.request.Request(
        "http://127.0.0.1:18765/api/v1/events",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req)
    except urllib.error.HTTPError as e:
        if e.code == 429:
            hit_429 = True
            break

check("超过限流阈值返回 429", hit_429)


# ── 8. 删除数据 API ────────────────────────────────────────────

print("\n[8] 删除数据")
req = urllib.request.Request(
    "http://127.0.0.1:18765/api/v1/data?device_id=test-device-001",
    method="DELETE"
)
resp = urllib.request.urlopen(req)
data = json.loads(resp.read())
check("DELETE /data 返回 200", resp.status == 200)
check("deleted == 4", data["deleted"] == 4, str(data))


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

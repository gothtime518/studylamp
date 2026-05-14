"""
WebSocket 端到端测试
运行：python3 test_ws.py
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
os.environ["STUDYLAMP_DB"] = os.path.join(_tmp_dir, "test_ws.db")
os.environ["STUDYLAMP_SERVER"] = "http://127.0.0.1:18767"
os.environ["STUDYLAMP_DEVICE_ID"] = "ws-test-001"

import config
config.DATA_DIR = _tmp_dir
config.EVENTS_FILE = os.path.join(_tmp_dir, "events.jsonl")

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
    uvicorn.run(app, host="127.0.0.1", port=18767, log_level="error")


server_thread = threading.Thread(target=start_server, daemon=True)
server_thread.start()

for _ in range(20):
    try:
        urllib.request.urlopen("http://127.0.0.1:18767/health", timeout=1)
        break
    except Exception:
        time.sleep(0.3)
else:
    print("❌ 服务器启动失败")
    sys.exit(1)

print("服务器已就绪\n")


# ── 1. WebSocket 连接 + 接收广播 ──────────────────────────────

print("[1] WebSocket 实时状态推送")

import websockets
import asyncio


async def ws_test():
    received = []
    uri = "ws://127.0.0.1:18767/api/v1/realtime/ws-test-001"

    async with websockets.connect(uri) as ws:
        # 连接后立即 POST push
        payload = json.dumps({"state": "studying"}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:18767/api/v1/realtime/ws-test-001/push",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)

        # 等待广播消息（最多 2 秒）
        try:
            msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
            received.append(json.loads(msg))
        except asyncio.TimeoutError:
            pass

        # ping/pong
        await ws.send("ping")
        pong = await asyncio.wait_for(ws.recv(), timeout=2.0)
        received.append({"pong": pong})

    return received


results = asyncio.run(ws_test())

check("收到广播消息", len(results) >= 1, str(results))
check("广播包含 state 字段", any("state" in r for r in results), str(results))
check("state == studying", any(r.get("state") == "studying" for r in results), str(results))
check("ping 收到 pong", any(r.get("pong") == "pong" for r in results), str(results))


# ── 2. 多客户端广播 ────────────────────────────────────────────

print("\n[2] 多客户端广播")


async def multi_client_test():
    uri = "ws://127.0.0.1:18767/api/v1/realtime/ws-test-001"
    received_a = []
    received_b = []

    async with websockets.connect(uri) as ws_a, websockets.connect(uri) as ws_b:
        # 推送一条状态
        payload = json.dumps({"state": "distracted"}).encode()
        req = urllib.request.Request(
            "http://127.0.0.1:18767/api/v1/realtime/ws-test-001/push",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        urllib.request.urlopen(req, timeout=5)

        # 两个客户端都应收到
        for ws, buf in [(ws_a, received_a), (ws_b, received_b)]:
            try:
                msg = await asyncio.wait_for(ws.recv(), timeout=2.0)
                buf.append(json.loads(msg))
            except asyncio.TimeoutError:
                pass

    return received_a, received_b


ra, rb = asyncio.run(multi_client_test())
check("客户端 A 收到广播", len(ra) >= 1, str(ra))
check("客户端 B 收到广播", len(rb) >= 1, str(rb))
check("两端 state 一致", (
    ra and rb and ra[0].get("state") == rb[0].get("state")
), f"A={ra} B={rb}")


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

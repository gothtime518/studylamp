import threading
import time
import json
import os
import urllib.request
import urllib.error
from config import EVENTS_FILE, DATA_DIR
from core.events import file_lock

SYNC_INTERVAL = 300
SERVER_URL = os.environ.get("STUDYLAMP_SERVER", "http://localhost:8000")
DEVICE_ID = os.environ.get("STUDYLAMP_DEVICE_ID", "mac-dev-001")


def push_realtime_state(state: str):
    """把当前摄像头状态推送到服务器，服务器再广播给 WebSocket 客户端"""
    payload = json.dumps({"state": state, "device_id": DEVICE_ID}).encode("utf-8")
    req = urllib.request.Request(
        f"{SERVER_URL}/api/v1/realtime/{DEVICE_ID}/push",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        urllib.request.urlopen(req, timeout=3)
    except Exception:
        pass


class CloudSync:
    def __init__(self):
        self._stop = threading.Event()
        self._thread = None

    def start(self):
        if self._thread and self._thread.is_alive():
            return
        self._stop.clear()
        self._thread = threading.Thread(target=self._loop, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def sync_now(self) -> dict:
        """立即同步，返回结果摘要"""
        pending = self._read_pending()
        if not pending:
            return {"synced": 0, "failed": 0}
        return self._upload(pending)

    # ── 内部 ──────────────────────────────────────────────────

    def _loop(self):
        while not self._stop.is_set():
            try:
                self.sync_now()
            except Exception as e:
                print(f"[sync] error: {e}")
            self._stop.wait(SYNC_INTERVAL)

    def _read_pending(self) -> list:
        if not os.path.exists(EVENTS_FILE):
            return []
        pending = []
        # 持锁读，避免与 write_event 的 append 交错读到半行
        with file_lock:
            with open(EVENTS_FILE, "r", encoding="utf-8") as f:
                for line in f:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                        if not e.get("synced", False):
                            pending.append(e)
                    except json.JSONDecodeError:
                        continue
        return pending

    def _upload(self, events: list) -> dict:
        payload = json.dumps({
            "device_id": DEVICE_ID,
            "events": events,
        }).encode("utf-8")

        req = urllib.request.Request(
            f"{SERVER_URL}/api/v1/events",
            data=payload,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(req, timeout=10) as resp:
                if resp.status == 200:
                    self._mark_synced(events)
                    return {"synced": len(events), "failed": 0}
                return {"synced": 0, "failed": len(events)}
        except urllib.error.URLError as e:
            print(f"[sync] upload failed: {e}")
            return {"synced": 0, "failed": len(events)}

    def _mark_synced(self, synced_events: list):
        """重写 JSONL，将已同步事件标记 synced=true。

        整个「读 → 改 → os.replace」必须在 file_lock 内原子完成：否则采集线程
        在此期间 append 到旧文件的新事件，会被 os.replace 覆盖而永久丢失。
        用 (timestamp, type) 组合作为匹配键，比单用 timestamp 更不易误伤同秒事件。
        """
        if not os.path.exists(EVENTS_FILE):
            return
        synced_keys = {(e.get("timestamp"), e.get("type")) for e in synced_events}
        tmp_path = EVENTS_FILE + ".tmp"
        with file_lock:
            with open(EVENTS_FILE, "r", encoding="utf-8") as fin, \
                 open(tmp_path, "w", encoding="utf-8") as fout:
                for line in fin:
                    line = line.strip()
                    if not line:
                        continue
                    try:
                        e = json.loads(line)
                        if (e.get("timestamp"), e.get("type")) in synced_keys:
                            e["synced"] = True
                        fout.write(json.dumps(e, ensure_ascii=False) + "\n")
                    except json.JSONDecodeError:
                        fout.write(line + "\n")
            os.replace(tmp_path, EVENTS_FILE)

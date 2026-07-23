import json
import os
import threading
from datetime import datetime, timezone
from config import DATA_DIR, EVENTS_FILE


# 保护 EVENTS_FILE 的读/写/重写。sync.py 重写文件时也必须持有这把锁，
# 否则同步线程 os.replace 会覆盖掉采集线程刚 append 的事件（数据丢失）。
# 用可重入锁，避免同一线程内嵌套加锁时死锁。
file_lock = threading.RLock()


def _ensure_dir():
    os.makedirs(DATA_DIR, exist_ok=True)


def write_event(event_type: str, details: dict):
    _ensure_dir()
    event = {
        "type": event_type,
        "timestamp": datetime.now(timezone.utc).astimezone().isoformat(),
        "details": details,
        "synced": False,
    }
    with file_lock:
        with open(EVENTS_FILE, "a", encoding="utf-8") as f:
            f.write(json.dumps(event, ensure_ascii=False) + "\n")
    return event


def read_today_events() -> list:
    _ensure_dir()
    if not os.path.exists(EVENTS_FILE):
        return []
    today = datetime.now().date().isoformat()
    events = []
    with file_lock:
        with open(EVENTS_FILE, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    e = json.loads(line)
                    if e.get("timestamp", "").startswith(today):
                        events.append(e)
                except json.JSONDecodeError:
                    continue
    return events


def today_summary() -> dict:
    events = read_today_events()
    study_minutes = 0
    posture_bad_count = 0
    phone_count = 0
    session_start = None

    for e in events:
        t = e["type"]
        if t == "session_start":
            session_start = e["timestamp"]
        elif t == "session_end" and session_start:
            start = datetime.fromisoformat(session_start)
            end = datetime.fromisoformat(e["timestamp"])
            # 用 total_seconds()：timedelta.seconds 只取 0–86399 秒、丢弃 .days，
            # 跨天 session 会被严重少算。max(0, ...) 防止时钟回拨导致的负时长。
            study_minutes += int(max(0, (end - start).total_seconds()) // 60)
            session_start = None
        elif t == "posture_bad":
            posture_bad_count += 1
        elif t == "activity_change":
            if e["details"].get("to") == "using_phone":
                phone_count += 1

    return {
        "study_minutes": study_minutes,
        "posture_bad_count": posture_bad_count,
        "phone_count": phone_count,
        "event_count": len(events),
    }

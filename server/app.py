from fastapi import FastAPI, Depends, HTTPException, UploadFile, File, Form
from fastapi.responses import HTMLResponse
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime, timedelta
from sqlalchemy.orm import Session
import threading
from server.models import StudyEvent, HomeworkAnalysis, Child, PointsLedger, init_db, get_session
from server.ai_summary import generate_daily_summary
from server.wechat import send_alert, send_daily_report
from server.homework_ai import analyze_homework
from server.points import calc_daily_points, calc_badges
import tempfile, os
import time as _time
from collections import defaultdict
from pathlib import Path

app = FastAPI(title="StudyLamp API", version="0.1.0")

_DASHBOARD_HTML = (Path(__file__).parent / "dashboard.html").read_text(encoding="utf-8")


@app.get("/", response_class=HTMLResponse)
def dashboard():
    return _DASHBOARD_HTML

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# ── 简单限流（内存，单进程）────────────────────────────────────
_rate_store: dict = defaultdict(list)
RATE_LIMIT = 60        # 每个 device_id 每分钟最多 60 次 POST /events
RATE_WINDOW = 60       # 秒


def _check_rate(device_id: str) -> bool:
    now = _time.time()
    window_start = now - RATE_WINDOW
    calls = _rate_store[device_id]
    # 清理过期记录
    _rate_store[device_id] = [t for t in calls if t > window_start]
    if len(_rate_store[device_id]) >= RATE_LIMIT:
        return False
    _rate_store[device_id].append(now)
    return True


@app.on_event("startup")
def startup():
    init_db()


# ── Schemas ───────────────────────────────────────────────────

class EventPayload(BaseModel):
    type: str
    timestamp: str
    details: dict = {}
    synced: bool = False


class BatchEventsRequest(BaseModel):
    device_id: str
    events: List[EventPayload]


class DailyReportQuery(BaseModel):
    device_id: str
    date: Optional[str] = None  # YYYY-MM-DD, 默认今天


# ── 采集端 → 云端 ─────────────────────────────────────────────

@app.post("/api/v1/events")
def receive_events(body: BatchEventsRequest, db: Session = Depends(get_session)):
    if not _check_rate(body.device_id):
        raise HTTPException(status_code=429, detail="Rate limit exceeded")
    inserted = 0
    for e in body.events:
        row = StudyEvent(
            device_id=body.device_id,
            event_type=e.type,
            timestamp=e.timestamp,
            details=e.details,
        )
        db.add(row)
        inserted += 1
    db.commit()

    # 实时告警：phone_detected / posture_bad 触发微信推送
    # 注意：传 device_id 而非 db，后台线程自己开新 session
    threading.Thread(
        target=_trigger_alerts,
        args=(body.device_id, [(e.type, e.details) for e in body.events]),
        daemon=True,
    ).start()

    # session_end 时自动生成日报 + 积分 + 推送
    if any(e.type == "session_end" for e in body.events):
        threading.Thread(
            target=_auto_daily_report,
            args=(body.device_id,),
            daemon=True,
        ).start()

    return {"accepted": inserted, "device_id": body.device_id}


# 告警去重：device_id + alert_type → 上次推送时间
_alert_last_sent: dict = {}
ALERT_COOLDOWN = 600  # 同类告警 10 分钟内只推一次


def _trigger_alerts(device_id: str, events: list):
    """后台线程：检查事件列表，触发微信告警（带去重）"""
    from server.models import engine as _engine
    from sqlalchemy.orm import Session as _Session
    with _Session(_engine) as db:
        child = db.query(Child).filter(Child.device_id == device_id).first()
        if not child:
            return
        openid = child.parent_openid

    now = _time.time()
    for event_type, details in events:
        if event_type == "phone_detected":
            key = f"{device_id}:phone"
            if now - _alert_last_sent.get(key, 0) >= ALERT_COOLDOWN:
                send_alert(openid, "玩手机", "检测到孩子拿起手机")
                _alert_last_sent[key] = now
        elif event_type == "posture_bad":
            key = f"{device_id}:posture"
            if now - _alert_last_sent.get(key, 0) >= ALERT_COOLDOWN:
                issues = details.get("issues", [])
                issue_str = "、".join(issues) if issues else "坐姿不良"
                send_alert(openid, "坐姿不良", issue_str)
                _alert_last_sent[key] = now


def _auto_daily_report(device_id: str):
    """session_end 后自动生成日报、计算积分、推送微信"""
    from server.models import engine as _engine
    from sqlalchemy.orm import Session as _Session
    today = datetime.utcnow().date().isoformat()

    with _Session(_engine) as db:
        rows = db.query(StudyEvent).filter(
            StudyEvent.device_id == device_id,
            StudyEvent.timestamp.startswith(today),
        ).all()
        study_minutes = 0
        posture_bad = 0
        phone_count = 0
        session_start = None
        for r in rows:
            if r.event_type == "session_start":
                session_start = r.timestamp
            elif r.event_type == "session_end" and session_start:
                start = datetime.fromisoformat(session_start)
                end = datetime.fromisoformat(r.timestamp)
                study_minutes += (end - start).seconds // 60
                session_start = None
            elif r.event_type == "posture_bad":
                posture_bad += 1
            elif r.event_type == "activity_change" and r.details.get("to") == "using_phone":
                phone_count += 1

        report = {
            "study_minutes": study_minutes,
            "posture_bad_count": posture_bad,
            "phone_count": phone_count,
            "event_count": len(rows),
        }
        summary = generate_daily_summary(report)

        child = db.query(Child).filter(Child.device_id == device_id).first()
        if child:
            h, m = divmod(study_minutes, 60)
            time_str = f"{h}小时{m}分钟" if h else f"{m}分钟"
            send_daily_report(child.parent_openid, summary[:20], time_str)


# ── 微信登录 ──────────────────────────────────────────────────

class WxLoginRequest(BaseModel):
    code: str


@app.post("/api/v1/auth/login")
def wx_login(body: WxLoginRequest):
    """
    微信 code 换 openid。
    生产环境需调用微信 jscode2session 接口，MVP 阶段返回 code 派生的临时 ID。
    """
    import os, urllib.request, json as _json
    app_id = os.environ.get("WECHAT_APP_ID", "")
    app_secret = os.environ.get("WECHAT_APP_SECRET", "")

    if app_id and app_secret:
        url = (
            f"https://api.weixin.qq.com/sns/jscode2session"
            f"?appid={app_id}&secret={app_secret}"
            f"&js_code={body.code}&grant_type=authorization_code"
        )
        try:
            with urllib.request.urlopen(url, timeout=10) as resp:
                data = _json.loads(resp.read())
                openid = data.get("openid", "")
                if openid:
                    return {"openid": openid}
        except Exception as e:
            print(f"[auth] wx login error: {e}")

    # 降级：用 code 派生临时 openid（仅开发用）
    tmp_openid = f"dev_{body.code[:8]}"
    return {"openid": tmp_openid, "dev_mode": True}


# ── 家长端查询 ────────────────────────────────────────────────

@app.get("/api/v1/report/daily/{date}")
def daily_report(date: str, device_id: str, db: Session = Depends(get_session)):
    rows = db.query(StudyEvent).filter(
        StudyEvent.device_id == device_id,
        StudyEvent.timestamp.startswith(date),
    ).all()

    study_minutes = 0
    posture_bad = 0
    phone_count = 0
    session_start = None

    for r in rows:
        if r.event_type == "session_start":
            session_start = r.timestamp
        elif r.event_type == "session_end" and session_start:
            start = datetime.fromisoformat(session_start)
            end = datetime.fromisoformat(r.timestamp)
            study_minutes += (end - start).seconds // 60
            session_start = None
        elif r.event_type == "posture_bad":
            posture_bad += 1
        elif r.event_type == "activity_change":
            if r.details.get("to") == "using_phone":
                phone_count += 1

    report = {
        "date": date,
        "device_id": device_id,
        "study_minutes": study_minutes,
        "posture_bad_count": posture_bad,
        "phone_count": phone_count,
        "event_count": len(rows),
    }
    report["ai_summary"] = generate_daily_summary(report)
    return report


@app.delete("/api/v1/data")
def delete_all_data(device_id: str, db: Session = Depends(get_session)):
    deleted = db.query(StudyEvent).filter(StudyEvent.device_id == device_id).delete()
    db.commit()
    return {"deleted": deleted}


class NotifyRequest(BaseModel):
    openid: str
    alert_type: str       # "坐姿不良" | "玩手机" | "长时间未休息"
    detail: str = ""


class DailyNotifyRequest(BaseModel):
    openid: str
    summary: str
    study_time: str


@app.post("/api/v1/notify/alert")
def notify_alert(body: NotifyRequest):
    ok = send_alert(body.openid, body.alert_type, body.detail)
    return {"sent": ok}


@app.post("/api/v1/notify/daily")
def notify_daily(body: DailyNotifyRequest):
    ok = send_daily_report(body.openid, body.summary, body.study_time)
    return {"sent": ok}


# ── 作业分析 ──────────────────────────────────────────────────

@app.post("/api/v1/homework")
async def upload_homework(
    device_id: str = Form(...),
    subject: str = Form("未知"),
    ocr_text: str = Form(""),
    file: UploadFile = File(...),
    db: Session = Depends(get_session),
):
    # 保存上传图片到临时文件
    suffix = os.path.splitext(file.filename)[1] or ".jpg"
    with tempfile.NamedTemporaryFile(suffix=suffix, delete=False) as tmp:
        tmp.write(await file.read())
        tmp_path = tmp.name

    try:
        result = analyze_homework(tmp_path, subject, ocr_text)
    finally:
        os.unlink(tmp_path)

    row = HomeworkAnalysis(
        device_id=device_id,
        subject=result.get("subject", subject),
        ocr_text=ocr_text,
        errors=result.get("errors", []),
        suggestions=result.get("suggestions", []),
        score_estimate=result.get("score_estimate"),
        summary=result.get("summary", ""),
    )
    db.add(row)
    db.commit()
    db.refresh(row)

    return {
        "id": row.id,
        "subject": row.subject,
        "errors": row.errors,
        "suggestions": row.suggestions,
        "score_estimate": row.score_estimate,
        "summary": row.summary,
        "created_at": row.created_at.isoformat(),
    }


@app.get("/api/v1/homework/{hw_id}/analysis")
def get_homework_analysis(hw_id: int, db: Session = Depends(get_session)):
    row = db.query(HomeworkAnalysis).filter(HomeworkAnalysis.id == hw_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    return {
        "id": row.id,
        "subject": row.subject,
        "errors": row.errors,
        "suggestions": row.suggestions,
        "score_estimate": row.score_estimate,
        "summary": row.summary,
        "created_at": row.created_at.isoformat(),
    }


class HomeworkFeedback(BaseModel):
    correct: bool           # AI 批改是否准确
    actual_score: Optional[int] = None
    comment: str = ""


@app.post("/api/v1/homework/{hw_id}/feedback")
def homework_feedback(hw_id: int, body: HomeworkFeedback, db: Session = Depends(get_session)):
    """T3.6: 家长反馈 AI 批改准确率，用于后续模型优化"""
    row = db.query(HomeworkAnalysis).filter(HomeworkAnalysis.id == hw_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    # 把反馈写入 details 字段（复用现有结构，不加新表）
    feedback = {
        "correct": body.correct,
        "actual_score": body.actual_score,
        "comment": body.comment,
    }
    # HomeworkAnalysis 没有 feedback 字段，用 suggestions 末尾追加标记
    # 实际生产中应加独立 feedback 表，这里 MVP 先用 JSON 存
    row.suggestions = list(row.suggestions or []) + [f"[feedback] correct={body.correct}"]
    db.commit()
    return {"accepted": True, "hw_id": hw_id}


@app.get("/api/v1/homework/recent")
def recent_homework(device_id: str, limit: int = 10, db: Session = Depends(get_session)):
    rows = db.query(HomeworkAnalysis).filter(
        HomeworkAnalysis.device_id == device_id
    ).order_by(HomeworkAnalysis.created_at.desc()).limit(limit).all()
    return [
        {
            "id": r.id,
            "subject": r.subject,
            "score_estimate": r.score_estimate,
            "summary": r.summary,
            "created_at": r.created_at.isoformat(),
        }
        for r in rows
    ]


# ── 周报 ──────────────────────────────────────────────────────

@app.get("/api/v1/report/weekly")
def weekly_report(device_id: str, db: Session = Depends(get_session)):
    today = datetime.utcnow().date()
    days_data = []
    for i in range(6, -1, -1):
        day = (today - timedelta(days=i)).isoformat()
        rows = db.query(StudyEvent).filter(
            StudyEvent.device_id == device_id,
            StudyEvent.timestamp.startswith(day),
        ).all()
        study_minutes = 0
        posture_bad = 0
        phone_count = 0
        session_start = None
        for r in rows:
            if r.event_type == "session_start":
                session_start = r.timestamp
            elif r.event_type == "session_end" and session_start:
                start = datetime.fromisoformat(session_start)
                end = datetime.fromisoformat(r.timestamp)
                study_minutes += (end - start).seconds // 60
                session_start = None
            elif r.event_type == "posture_bad":
                posture_bad += 1
            elif r.event_type == "activity_change" and r.details.get("to") == "using_phone":
                phone_count += 1
        days_data.append({
            "date": day,
            "study_minutes": study_minutes,
            "posture_bad_count": posture_bad,
            "phone_count": phone_count,
        })
    return {"device_id": device_id, "days": days_data}


# ── 积分 + 徽章 ───────────────────────────────────────────────

@app.post("/api/v1/points/calc")
def calc_points(device_id: str, date: str, db: Session = Depends(get_session)):
    """根据当天日报计算并写入积分"""
    rows = db.query(StudyEvent).filter(
        StudyEvent.device_id == device_id,
        StudyEvent.timestamp.startswith(date),
    ).all()
    study_minutes = 0
    posture_bad = 0
    phone_count = 0
    session_start = None
    for r in rows:
        if r.event_type == "session_start":
            session_start = r.timestamp
        elif r.event_type == "session_end" and session_start:
            start = datetime.fromisoformat(session_start)
            end = datetime.fromisoformat(r.timestamp)
            study_minutes += (end - start).seconds // 60
            session_start = None
        elif r.event_type == "posture_bad":
            posture_bad += 1
        elif r.event_type == "activity_change" and r.details.get("to") == "using_phone":
            phone_count += 1

    # 计算连续学习天数
    streak = _calc_streak(device_id, date, db)
    ledger = calc_daily_points(study_minutes, posture_bad, phone_count, streak)

    for item in ledger:
        db.add(PointsLedger(
            device_id=device_id,
            date=date,
            points=item["points"],
            reason=item["reason"],
        ))
    db.commit()

    total_today = sum(i["points"] for i in ledger)
    total_all = db.query(PointsLedger).filter(
        PointsLedger.device_id == device_id
    ).with_entities(PointsLedger.points).all()
    grand_total = sum(r[0] for r in total_all)

    stats = {
        "study_minutes": study_minutes,
        "posture_bad_count": posture_bad,
        "phone_count": phone_count,
        "streak": streak,
        "total_days": len(set(
            r[0] for r in db.query(PointsLedger.date).filter(
                PointsLedger.device_id == device_id
            ).all()
        )),
    }
    badges = calc_badges(stats)

    return {
        "date": date,
        "today_points": total_today,
        "total_points": grand_total,
        "ledger": ledger,
        "badges": badges,
        "streak": streak,
    }


@app.get("/api/v1/points/summary")
def points_summary(device_id: str, db: Session = Depends(get_session)):
    rows = db.query(PointsLedger).filter(PointsLedger.device_id == device_id).all()
    total = sum(r.points for r in rows)
    today = datetime.utcnow().date().isoformat()
    today_pts = sum(r.points for r in rows if r.date == today)
    streak = _calc_streak(device_id, today, db)
    # active_days 从 StudyEvent 计算（有 session_start 的天数），不依赖积分记录
    active_days = len(set(
        r[0][:10] for r in db.query(StudyEvent.timestamp).filter(
            StudyEvent.device_id == device_id,
            StudyEvent.event_type == "session_start",
        ).all()
    ))
    stats = {"study_minutes": 0, "posture_bad_count": 0, "phone_count": 0,
             "streak": streak, "total_days": active_days}
    badges = calc_badges(stats)
    return {
        "total_points": total,
        "today_points": today_pts,
        "streak": streak,
        "active_days": active_days,
        "badges": badges,
    }


def _calc_streak(device_id: str, up_to_date: str, db: Session) -> int:
    """计算截止某天的连续学习天数"""
    dates = set(
        r[0] for r in db.query(PointsLedger.date).filter(
            PointsLedger.device_id == device_id,
            PointsLedger.date <= up_to_date,
        ).all()
    )
    streak = 0
    check = datetime.fromisoformat(up_to_date).date()
    while check.isoformat() in dates:
        streak += 1
        check -= timedelta(days=1)
    return streak


# ── 多孩子管理 ────────────────────────────────────────────────

class ChildCreate(BaseModel):
    parent_openid: str
    name: str
    device_id: str


@app.post("/api/v1/children")
def add_child(body: ChildCreate, db: Session = Depends(get_session)):
    existing = db.query(Child).filter(Child.device_id == body.device_id).first()
    if existing:
        raise HTTPException(status_code=409, detail="Device already bound")
    child = Child(parent_openid=body.parent_openid, name=body.name, device_id=body.device_id)
    db.add(child)
    db.commit()
    db.refresh(child)
    return {"id": child.id, "name": child.name, "device_id": child.device_id}


@app.get("/api/v1/children")
def list_children(parent_openid: str, db: Session = Depends(get_session)):
    rows = db.query(Child).filter(Child.parent_openid == parent_openid).all()
    return [{"id": r.id, "name": r.name, "device_id": r.device_id} for r in rows]


@app.delete("/api/v1/children/{child_id}")
def remove_child(child_id: int, db: Session = Depends(get_session)):
    row = db.query(Child).filter(Child.id == child_id).first()
    if not row:
        raise HTTPException(status_code=404, detail="Not found")
    db.delete(row)
    db.commit()
    return {"deleted": child_id}


@app.get("/health")
def health():
    return {"status": "ok", "time": datetime.utcnow().isoformat()}


@app.get("/api/v1/metrics")
def metrics(db: Session = Depends(get_session)):
    """T2.10: 轻量监控端点，返回系统级统计"""
    total_events = db.query(StudyEvent).count()
    total_devices = db.query(StudyEvent.device_id).distinct().count()
    total_homework = db.query(HomeworkAnalysis).count()
    total_children = db.query(Child).count()
    today = datetime.utcnow().date().isoformat()
    today_events = db.query(StudyEvent).filter(
        StudyEvent.timestamp.startswith(today)
    ).count()
    return {
        "total_events": total_events,
        "today_events": today_events,
        "total_devices": total_devices,
        "total_homework_analyses": total_homework,
        "total_children": total_children,
        "time": datetime.utcnow().isoformat(),
    }


# ── WebSocket 实时状态推送 ─────────────────────────────────────

from fastapi import WebSocket, WebSocketDisconnect
import asyncio
import json as _json

# 连接池：device_id → set of WebSocket
# 所有操作都在同一个 asyncio 事件循环里，无需加锁
_ws_connections: dict = {}


class RealtimeState(BaseModel):
    state: str
    device_id: str = ""


@app.websocket("/api/v1/realtime/{device_id}")
async def realtime_ws(websocket: WebSocket, device_id: str):
    """家长端小程序连接，接收采集端实时状态推送"""
    await websocket.accept()
    _ws_connections.setdefault(device_id, set()).add(websocket)
    try:
        while True:
            data = await websocket.receive_text()
            if data == "ping":
                await websocket.send_text("pong")
    except WebSocketDisconnect:
        pass
    finally:
        _ws_connections.get(device_id, set()).discard(websocket)


async def _broadcast_state(device_id: str, state: dict):
    """向所有监听该设备的 WebSocket 客户端广播状态"""
    conns = list(_ws_connections.get(device_id, set()))
    for ws in conns:
        try:
            await ws.send_text(_json.dumps(state, ensure_ascii=False))
        except Exception:
            pass


@app.post("/api/v1/realtime/{device_id}/push")
async def push_state(device_id: str, body: RealtimeState):
    """采集端推送当前状态（供 Mac 端调用）"""
    await _broadcast_state(device_id, {"state": body.state, "device_id": device_id})
    return {"pushed": len(_ws_connections.get(device_id, set()))}

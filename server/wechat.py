import os
import json
import urllib.request
import urllib.error

WECHAT_APP_ID = os.environ.get("WECHAT_APP_ID", "")
WECHAT_APP_SECRET = os.environ.get("WECHAT_APP_SECRET", "")

# 微信订阅消息模板 ID（需在微信公众平台申请）
TEMPLATE_ID_ALERT = os.environ.get("WECHAT_TEMPLATE_ALERT", "")
TEMPLATE_ID_DAILY = os.environ.get("WECHAT_TEMPLATE_DAILY", "")

_access_token_cache = {"token": "", "expires_at": 0}


def get_access_token() -> str:
    import time
    if _access_token_cache["token"] and time.time() < _access_token_cache["expires_at"]:
        return _access_token_cache["token"]

    if not WECHAT_APP_ID or not WECHAT_APP_SECRET:
        return ""

    url = (
        f"https://api.weixin.qq.com/cgi-bin/token"
        f"?grant_type=client_credential"
        f"&appid={WECHAT_APP_ID}"
        f"&secret={WECHAT_APP_SECRET}"
    )
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            data = json.loads(resp.read())
            token = data.get("access_token", "")
            expires_in = data.get("expires_in", 7200)
            _access_token_cache["token"] = token
            _access_token_cache["expires_at"] = time.time() + expires_in - 60
            return token
    except Exception as e:
        print(f"[wechat] get_access_token error: {e}")
        return ""


def send_alert(openid: str, alert_type: str, detail: str) -> bool:
    """
    发送实时告警（坐姿不良、玩手机等）
    alert_type: "坐姿不良" | "玩手机" | "长时间未休息"
    """
    token = get_access_token()
    if not token or not TEMPLATE_ID_ALERT:
        print(f"[wechat] alert skipped (no token/template): {alert_type} - {detail}")
        return False

    return _send_subscribe_message(token, openid, TEMPLATE_ID_ALERT, {
        "thing1": {"value": alert_type},
        "thing2": {"value": detail[:20]},
    })


def send_daily_report(openid: str, summary: str, study_time: str) -> bool:
    """发送每日学习日报"""
    token = get_access_token()
    if not token or not TEMPLATE_ID_DAILY:
        print(f"[wechat] daily report skipped (no token/template)")
        return False

    return _send_subscribe_message(token, openid, TEMPLATE_ID_DAILY, {
        "thing1": {"value": study_time},
        "thing2": {"value": summary[:20]},
    })


def _send_subscribe_message(token: str, openid: str, template_id: str, data: dict) -> bool:
    payload = json.dumps({
        "touser": openid,
        "template_id": template_id,
        "data": data,
    }).encode("utf-8")

    url = f"https://api.weixin.qq.com/cgi-bin/message/subscribe/send?access_token={token}"
    req = urllib.request.Request(url, data=payload,
                                  headers={"Content-Type": "application/json"},
                                  method="POST")
    try:
        with urllib.request.urlopen(req, timeout=10) as resp:
            result = json.loads(resp.read())
            ok = result.get("errcode", -1) == 0
            if not ok:
                print(f"[wechat] send failed: {result}")
            return ok
    except Exception as e:
        print(f"[wechat] send error: {e}")
        return False

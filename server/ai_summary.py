import os
import json
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def generate_daily_summary(report: dict) -> str:
    """
    根据日报数据生成 AI 摘要，返回中文建议文字。
    如果没有 API Key 或调用失败，返回模板文字。
    """
    if not GEMINI_API_KEY:
        return _template_summary(report)

    prompt = _build_prompt(report)
    try:
        return _call_gemini(prompt)
    except Exception as e:
        print(f"[gemini] error: {e}")
        return _template_summary(report)


def _build_prompt(report: dict) -> str:
    h, m = divmod(report.get("study_minutes", 0), 60)
    time_str = f"{h}小时{m}分钟" if h else f"{m}分钟"
    return f"""你是一个关心孩子学习的 AI 助手，请根据以下今日学习数据，用温和、鼓励的语气给家长写一段简短的学习总结（100字以内，中文）。

数据：
- 学习时长：{time_str}
- 坐姿提醒次数：{report.get('posture_bad_count', 0)} 次
- 玩手机次数：{report.get('phone_count', 0)} 次
- 总记录事件：{report.get('event_count', 0)} 条

要求：
1. 先肯定孩子的努力
2. 如有坐姿或手机问题，委婉提出
3. 给出一条具体建议
4. 不要用"根据数据"等机械表达"""


def _call_gemini(prompt: str) -> str:
    payload = json.dumps({
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"maxOutputTokens": 200, "temperature": 0.7},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        data = json.loads(resp.read())
        return data["candidates"][0]["content"]["parts"][0]["text"].strip()


def _template_summary(report: dict) -> str:
    h, m = divmod(report.get("study_minutes", 0), 60)
    time_str = f"{h}小时{m}分钟" if h else f"{m}分钟"
    posture = report.get("posture_bad_count", 0)
    phone = report.get("phone_count", 0)

    parts = [f"今天学习了{time_str}，很棒！"]
    if posture > 2:
        parts.append(f"坐姿提醒了{posture}次，记得保持挺胸抬头。")
    if phone > 0:
        parts.append(f"有{phone}次拿起手机，学习时尽量把手机放远一点。")
    if posture == 0 and phone == 0:
        parts.append("坐姿和专注度都很好，继续保持！")
    return "".join(parts)

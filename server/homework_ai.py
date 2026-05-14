import os
import json
import base64
import urllib.request
import urllib.error

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
GEMINI_MODEL = "gemini-2.0-flash"
GEMINI_URL = f"https://generativelanguage.googleapis.com/v1beta/models/{GEMINI_MODEL}:generateContent"


def analyze_homework(image_path: str, subject: str, ocr_text: str = "") -> dict:
    """
    用 Gemini Vision 分析作业图片，返回批改结果。
    无 API Key 时返回占位结果。
    """
    if not GEMINI_API_KEY:
        return _placeholder_result(subject)

    try:
        return _call_gemini_vision(image_path, subject, ocr_text)
    except Exception as e:
        print(f"[homework] gemini error: {e}")
        return _placeholder_result(subject)


def _call_gemini_vision(image_path: str, subject: str, ocr_text: str) -> dict:
    with open(image_path, "rb") as f:
        image_b64 = base64.b64encode(f.read()).decode("utf-8")

    ext = os.path.splitext(image_path)[1].lower()
    mime = "image/jpeg" if ext in (".jpg", ".jpeg") else "image/png"

    ocr_hint = f"\n\nOCR 识别文字（供参考）：\n{ocr_text}" if ocr_text else ""
    prompt = f"""你是一位经验丰富的{subject}老师，请分析这张作业图片。{ocr_hint}

请用 JSON 格式返回以下内容（不要加 markdown 代码块）：
{{
  "subject": "{subject}",
  "errors": ["错误1描述", "错误2描述"],
  "suggestions": ["建议1", "建议2"],
  "score_estimate": 85,
  "summary": "一句话总结"
}}

要求：
- errors 列出具体错误，没有则为空数组
- suggestions 给出针对性建议
- score_estimate 估计得分（0-100）
- summary 用温和鼓励的语气"""

    payload = json.dumps({
        "contents": [{
            "parts": [
                {"text": prompt},
                {"inline_data": {"mime_type": mime, "data": image_b64}},
            ]
        }],
        "generationConfig": {"maxOutputTokens": 500, "temperature": 0.3},
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{GEMINI_URL}?key={GEMINI_API_KEY}",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read())
        text = data["candidates"][0]["content"]["parts"][0]["text"].strip()
        # 清理可能的 markdown 代码块
        text = text.replace("```json", "").replace("```", "").strip()
        return json.loads(text)


def _placeholder_result(subject: str) -> dict:
    return {
        "subject": subject,
        "errors": [],
        "suggestions": ["请配置 GEMINI_API_KEY 以启用 AI 批改功能"],
        "score_estimate": None,
        "summary": "AI 批改功能未启用",
    }

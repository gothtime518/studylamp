from dataclasses import dataclass
from typing import Optional
import re

# 科目关键词（本地规则匹配，不需要模型）
SUBJECT_KEYWORDS = {
    "数学": ["数学", "math", "计算", "方程", "几何", "代数", "分数", "小数", "面积", "体积",
             "加法", "减法", "乘法", "除法", "证明", "函数", "三角"],
    "语文": ["语文", "作文", "阅读", "古诗", "词语", "造句", "拼音", "汉字", "课文",
             "段落", "修辞", "成语", "文言文"],
    "英语": ["english", "英语", "单词", "语法", "阅读理解", "完形填空", "词汇",
             "listening", "writing", "grammar", "vocabulary"],
    "物理": ["物理", "physics", "力", "速度", "加速度", "电路", "电流", "电压", "光学"],
    "化学": ["化学", "chemistry", "元素", "化合物", "反应", "分子", "原子", "溶液"],
    "生物": ["生物", "biology", "细胞", "基因", "遗传", "生态", "植物", "动物"],
    "历史": ["历史", "history", "朝代", "战争", "年代", "事件", "人物"],
    "地理": ["地理", "geography", "地图", "气候", "地形", "经纬度"],
}


@dataclass
class OCRResult:
    text: str = ""
    subject: str = "未知"
    confidence: float = 0.0
    available: bool = False  # PaddleOCR 是否可用


class HomeworkOCR:
    def __init__(self):
        self._ocr = None
        self._available = False
        self._try_init()

    def _try_init(self):
        try:
            from paddleocr import PaddleOCR
            self._ocr = PaddleOCR(use_angle_cls=True, lang="ch", show_log=False)
            self._available = True
        except ImportError:
            print("[ocr] PaddleOCR not installed, OCR disabled")
        except Exception as e:
            print(f"[ocr] init error: {e}")

    def extract(self, image_path: str) -> OCRResult:
        if not self._available or self._ocr is None:
            return OCRResult(available=False)

        try:
            result = self._ocr.ocr(image_path, cls=True)
            lines = []
            for line in (result[0] or []):
                text, conf = line[1]
                if conf > 0.5:
                    lines.append(text)
            full_text = "\n".join(lines)
            subject = self._classify_subject(full_text)
            return OCRResult(
                text=full_text,
                subject=subject,
                confidence=0.85 if lines else 0.0,
                available=True,
            )
        except Exception as e:
            print(f"[ocr] extract error: {e}")
            return OCRResult(available=True, text="", subject="未知", confidence=0.0)

    def _classify_subject(self, text: str) -> str:
        text_lower = text.lower()
        scores = {}
        for subject, keywords in SUBJECT_KEYWORDS.items():
            score = sum(1 for kw in keywords if kw.lower() in text_lower)
            if score > 0:
                scores[subject] = score
        if not scores:
            return "未知"
        return max(scores, key=scores.get)

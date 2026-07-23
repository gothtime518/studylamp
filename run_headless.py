#!/usr/bin/env python3
"""
StudyLamp 无界面入口（树莓派 / Linux 服务器用）

与 main.py（macOS 菜单栏应用）等价，但去掉 rumps / osascript 等 Mac 专属依赖：
- 不弹菜单栏图标，状态变化打印到日志
- 复用 core 的 CameraLoop / CloudSync / HomeworkOCR，逻辑与 Mac 版一致
- 作业拍照上传逻辑与 main.py 相同

用法：
    python3 run_headless.py
环境变量：
    STUDYLAMP_SERVER     后端地址（默认 http://localhost:8000）
    STUDYLAMP_DEVICE_ID  设备标识（默认 rpi-dev-001）
    STUDYLAMP_DATA_DIR   数据目录（默认按平台选择，见 config.py）
"""
import os
import sys
import json
import time
import signal
import logging
import threading
import urllib.request

from core.camera import CameraLoop
from core.sync import CloudSync
from core.ocr import HomeworkOCR
from core.privacy_check import run_check
from core.events import today_summary

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
)
log = logging.getLogger("studylamp")

DEVICE_ID = os.environ.get("STUDYLAMP_DEVICE_ID", "rpi-dev-001")
SERVER_URL = os.environ.get("STUDYLAMP_SERVER", "http://localhost:8000")

STATE_LABELS = {
    "studying":   "学习中（专注）",
    "warning":    "学习中（坐姿注意）",
    "distracted": "分心了",
    "absent":     "未检测到人",
}


class HeadlessApp:
    def __init__(self):
        self._camera = CameraLoop(on_state_change=self._on_state_change)
        self._sync = CloudSync()
        self._ocr = HomeworkOCR()
        self._current_state = None
        self._stop = threading.Event()
        self._camera.register_homework_callback(self._on_homework_captured)

    # ── 生命周期 ──────────────────────────────────────────────

    def start(self):
        # 启动隐私自查（仅记录，不阻塞）
        try:
            result = run_check(verbose=False)
            if not result["all_passed"]:
                failed = [r["name"] for r in result["results"]
                          if not r["passed"] and not r["manual"]]
                log.warning("隐私合规自查未全部通过：%s", ", ".join(failed))
        except Exception as e:
            log.error("隐私自查出错：%s", e)

        log.info("StudyLamp 启动 | device=%s | server=%s", DEVICE_ID, SERVER_URL)
        self._camera.start()
        self._sync.start()

    def stop(self):
        log.info("正在停止…")
        self._camera.stop()
        self._sync.stop()
        self._stop.set()

    def run_forever(self):
        self.start()
        # 主线程等待信号；子线程（camera/sync）为 daemon
        try:
            while not self._stop.is_set():
                self._stop.wait(1)
        except KeyboardInterrupt:
            pass
        finally:
            self.stop()

    # ── 回调 ──────────────────────────────────────────────────

    def _on_state_change(self, state: str):
        if state != self._current_state:
            self._current_state = state
            log.info("状态：%s", STATE_LABELS.get(state, state))

    def _on_homework_captured(self, image_path: str):
        """摄像头切到 studying 时触发：OCR → 上传服务器。逻辑与 main.py 一致。"""
        try:
            ocr_result = self._ocr.extract(image_path)
            subject = ocr_result.subject if ocr_result.available else "未知"
            ocr_text = ocr_result.text if ocr_result.available else ""
            summary = self._upload_homework(image_path, subject, ocr_text)
            if summary:
                log.info("作业分析（%s）：%s", subject, summary[:80])
        except Exception as e:
            log.error("作业上传失败：%s", e)

    def _upload_homework(self, image_path: str, subject: str, ocr_text: str) -> str:
        boundary = "----StudyLampBoundary"
        parts = []

        def field(name, value):
            return (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                f"{value}\r\n"
            ).encode("utf-8")

        parts.append(field("device_id", DEVICE_ID))
        parts.append(field("subject", subject))
        parts.append(field("ocr_text", ocr_text[:500]))

        with open(image_path, "rb") as f:
            img_data = f.read()
        filename = os.path.basename(image_path)
        file_header = (
            f"--{boundary}\r\n"
            f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n"
        ).encode("utf-8")
        parts.append(file_header + img_data + b"\r\n")
        parts.append(f"--{boundary}--\r\n".encode("utf-8"))

        body = b"".join(parts)
        req = urllib.request.Request(
            f"{SERVER_URL}/api/v1/homework",
            data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
            method="POST",
        )
        with urllib.request.urlopen(req, timeout=30) as resp:
            result = json.loads(resp.read())
            return result.get("summary", "")


def main():
    app = HeadlessApp()

    # 收到 SIGTERM（systemd stop）时优雅退出
    def _handle_term(signum, frame):
        app.stop()
    signal.signal(signal.SIGTERM, _handle_term)

    app.run_forever()


if __name__ == "__main__":
    main()

import rumps
import threading
import subprocess
import os
import urllib.request
import urllib.error
from core.camera import CameraLoop
from core.events import today_summary
from core.sync import CloudSync
from core.config_watcher import ConfigWatcher
from core.privacy_check import run_check
from core.ocr import HomeworkOCR
from ui.preview import PreviewWindow


def _notify(title: str, message: str):
    """用 osascript 发送 macOS 通知，不阻塞主线程"""
    script = f'display notification "{message}" with title "{title}"'
    subprocess.Popen(["osascript", "-e", script],
                     stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

DEVICE_ID = os.environ.get("STUDYLAMP_DEVICE_ID", "mac-dev-001")
SERVER_URL = os.environ.get("STUDYLAMP_SERVER", "http://localhost:8000")

# 状态 → 菜单栏图标文字（rumps 用 title 显示文字或 emoji）
STATE_ICONS = {
    "studying":   "🟢",
    "warning":    "🟡",
    "distracted": "🔴",
    "absent":     "⚫",
}

STATE_LABELS = {
    "studying":   "学习中（专注）",
    "warning":    "学习中（坐姿注意）",
    "distracted": "分心了",
    "absent":     "未检测到人",
}


class StudyLampApp(rumps.App):
    def __init__(self):
        super().__init__("⚫", quit_button=None)

        self._camera = CameraLoop(on_state_change=self._on_state_change)
        self._preview = PreviewWindow(self._camera)
        self._sync = CloudSync()
        self._ocr = HomeworkOCR()
        self._watcher = ConfigWatcher()
        self._watcher.on_reload(self._on_config_reload)
        self._watcher.start()
        self._running = False
        self._current_state = "absent"
        self._pending_state = None  # 子线程写入，主线程轮询读取

        # 注册作业拍照回调
        self._camera.register_homework_callback(self._on_homework_captured)

        # 菜单项
        self.status_item = rumps.MenuItem("状态：未启动")
        self.status_item.set_callback(None)

        self.device_item = rumps.MenuItem(f"设备 ID：{DEVICE_ID}")
        self.device_item.set_callback(None)

        self.toggle_item = rumps.MenuItem("▶ 开始监测", callback=self.toggle_monitoring)
        self.preview_item = rumps.MenuItem("打开预览窗口", callback=self.toggle_preview)
        self.stats_item = rumps.MenuItem("今日统计", callback=self.show_stats)
        self.sync_item = rumps.MenuItem("立即同步", callback=self.sync_now)
        self.privacy_item = rumps.MenuItem("隐私合规检查", callback=self.show_privacy_check)
        self.quit_item = rumps.MenuItem("退出", callback=self.quit_app)

        self.menu = [
            self.status_item,
            self.device_item,
            None,
            self.toggle_item,
            self.preview_item,
            None,
            self.stats_item,
            self.sync_item,
            None,
            self.privacy_item,
            None,
            self.quit_item,
        ]

        # 启动时后台运行隐私自查
        threading.Thread(target=self._startup_privacy_check, daemon=True).start()

    # ── 启动隐私自查 ──────────────────────────────────────────

    def _startup_privacy_check(self):
        result = run_check(verbose=False)
        if not result["all_passed"]:
            failed = [r["name"] for r in result["results"]
                      if not r["passed"] and not r["manual"]]
            _notify("隐私合规警告", f"自动检查未通过：{', '.join(failed)}")

    def show_privacy_check(self, _):
        try:
            result = run_check(verbose=False)
            auto = result["results"]
            passed = sum(1 for r in auto if r["passed"] and not r["manual"])
            total = sum(1 for r in auto if not r["manual"])
            _notify("隐私合规自查", f"自动检查 {passed}/{total} 通过")
        except Exception as e:
            print(f"[privacy] error: {e}", flush=True)

    # ── 监测开关 ──────────────────────────────────────────────

    def toggle_monitoring(self, _):
        if self._running:
            self._camera.stop()
            self._sync.stop()
            self._running = False
            self.toggle_item.title = "▶ 开始监测"
            self.title = "⚫"
            self.status_item.title = "状态：已停止"
        else:
            self._camera.start()
            self._sync.start()
            self._running = True
            self.toggle_item.title = "⏹ 停止监测"
            self.status_item.title = "状态：启动中…"

    # ── 预览窗口 ──────────────────────────────────────────────

    def toggle_preview(self, _):
        if self._preview._running:
            self._preview.hide()
            self.preview_item.title = "打开预览窗口"
        else:
            if not self._running:
                _notify("StudyLamp", "请先点击「开始监测」")
                return
            self._preview.show()
            self.preview_item.title = "关闭预览窗口"

    # ── 立即同步 ──────────────────────────────────────────────

    def sync_now(self, _):
        def _do_sync():
            try:
                result = self._sync.sync_now()
                if result["synced"] > 0:
                    _notify("同步完成", f"已上传 {result['synced']} 条事件")
                elif result["failed"] > 0:
                    _notify("同步失败", "请检查网络或服务器连接")
                else:
                    _notify("同步", "没有待同步的事件")
            except Exception as e:
                print(f"[sync] error: {e}", flush=True)
        threading.Thread(target=_do_sync, daemon=True).start()

    # ── 配置热更新回调 ────────────────────────────────────────

    def _on_config_reload(self, config):
        _notify("StudyLamp", "配置已更新")

    # ── 作业拍照回调 ──────────────────────────────────────────

    def _on_homework_captured(self, image_path: str):
        """摄像头切换到 studying 时触发：OCR → 上传服务器"""
        ocr_result = self._ocr.extract(image_path)
        subject = ocr_result.subject if ocr_result.available else "未知"
        ocr_text = ocr_result.text if ocr_result.available else ""

        try:
            import json as _json
            boundary = "----StudyLampBoundary"
            body_parts = []

            def field(name, value):
                return (
                    f"--{boundary}\r\n"
                    f'Content-Disposition: form-data; name="{name}"\r\n\r\n'
                    f"{value}\r\n"
                ).encode("utf-8")

            body_parts.append(field("device_id", DEVICE_ID))
            body_parts.append(field("subject", subject))
            body_parts.append(field("ocr_text", ocr_text[:500]))

            with open(image_path, "rb") as f:
                img_data = f.read()
            filename = os.path.basename(image_path)
            # 修复：先把 header 字符串整体 encode，再拼接 bytes
            file_header = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
                f"Content-Type: image/jpeg\r\n\r\n"
            ).encode("utf-8")
            body_parts.append(file_header + img_data + b"\r\n")
            body_parts.append(f"--{boundary}--\r\n".encode("utf-8"))

            body = b"".join(body_parts)
            req = urllib.request.Request(
                f"{SERVER_URL}/api/v1/homework",
                data=body,
                headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
                method="POST",
            )
            with urllib.request.urlopen(req, timeout=30) as resp:
                result = _json.loads(resp.read())
                summary = result.get("summary", "")
                if summary:
                    _notify(f"作业分析（{subject}）", summary[:50])
        except Exception as e:
            print(f"[homework] upload error: {e}")

    # ── 今日统计 ──────────────────────────────────────────────

    def show_stats(self, _):
        try:
            s = today_summary()
            h, m = divmod(s["study_minutes"], 60)
            time_str = f"{h}小时{m}分钟" if h else f"{m}分钟"
            msg = f"学习{time_str} | 坐姿提醒{s['posture_bad_count']}次 | 玩手机{s['phone_count']}次"
            _notify("今日学习统计", msg)
        except Exception as e:
            print(f"[stats] error: {e}", flush=True)

    # ── 状态回调（来自 camera 线程）────────────────────────────

    def _on_state_change(self, state: str):
        self._pending_state = state

    @rumps.timer(1)
    def _poll_state(self, _):
        """主线程定时轮询，安全更新 UI"""
        state = self._pending_state
        if state is None or state == self._current_state:
            return
        self._current_state = state
        self.title = STATE_ICONS.get(state, "⚫")
        self.status_item.title = f"状态：{STATE_LABELS.get(state, '')}"

    # ── 退出 ──────────────────────────────────────────────────

    def quit_app(self, _):
        if self._running:
            self._camera.stop()
            self._sync.stop()
        rumps.quit_application()


if __name__ == "__main__":
    StudyLampApp().run()

import subprocess
import threading
import tempfile
import time
import os
import cv2


class PreviewWindow:
    """
    预览窗口：将帧写入临时文件，用独立 Python 子进程显示。
    避免 cv2.imshow 在 macOS 非主线程无法显示窗口的问题。
    """

    def __init__(self, camera_loop):
        self._camera = camera_loop
        self._thread = None
        self._running = False
        self._proc = None
        self._frame_path = os.path.join(tempfile.gettempdir(), "studylamp_preview.jpg")

    def show(self):
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(target=self._write_frames, daemon=True)
        self._thread.start()
        self._proc = subprocess.Popen(
            ["python", "-c", _VIEWER_SCRIPT, self._frame_path],
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

    def hide(self):
        self._running = False
        if self._proc:
            self._proc.terminate()
            self._proc = None

    def _write_frames(self):
        while self._running:
            frame = self._camera.get_latest_frame()
            if frame is not None:
                cv2.imwrite(self._frame_path, frame)
            time.sleep(0.05)
            if self._proc and self._proc.poll() is not None:
                self._running = False
                break


_VIEWER_SCRIPT = """
import sys, cv2, os, time

path = sys.argv[1]
win = "StudyLamp Preview"
cv2.namedWindow(win, cv2.WINDOW_NORMAL)
cv2.resizeWindow(win, 640, 480)

while True:
    if os.path.exists(path):
        frame = cv2.imread(path)
        if frame is not None:
            cv2.imshow(win, frame)
    key = cv2.waitKey(33)
    if key == ord('q') or key == 27:
        break
    try:
        if cv2.getWindowProperty(win, cv2.WND_PROP_VISIBLE) < 1:
            break
    except cv2.error:
        break

cv2.destroyAllWindows()
"""

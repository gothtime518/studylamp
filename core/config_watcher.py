"""
配置热更新：监听 config.py 文件变化，自动重新加载配置值
用法：ConfigWatcher().start()
"""
import threading
import time
import os
import importlib
import sys


class ConfigWatcher:
    def __init__(self, config_path: str = None):
        if config_path is None:
            config_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), "config.py")
        self._path = config_path
        self._mtime = self._get_mtime()
        self._stop = threading.Event()
        self._thread = None
        self._callbacks = []

    def on_reload(self, callback):
        """注册配置重载回调"""
        self._callbacks.append(callback)
        return self

    def start(self):
        self._stop.clear()
        self._thread = threading.Thread(target=self._watch, daemon=True)
        self._thread.start()

    def stop(self):
        self._stop.set()

    def _get_mtime(self) -> float:
        try:
            return os.path.getmtime(self._path)
        except OSError:
            return 0.0

    def _watch(self):
        while not self._stop.is_set():
            mtime = self._get_mtime()
            if mtime != self._mtime:
                self._mtime = mtime
                self._reload()
            self._stop.wait(2)  # 每 2 秒检查一次

    def _reload(self):
        try:
            import config
            importlib.reload(config)
            print("[config] reloaded")
            for cb in self._callbacks:
                try:
                    cb(config)
                except Exception as e:
                    print(f"[config] callback error: {e}")
        except Exception as e:
            print(f"[config] reload error: {e}")

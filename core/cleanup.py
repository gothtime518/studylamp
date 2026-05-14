"""
数据保留清理：删除超过 N 天的本地图片缓存
集成到 CameraLoop 启动时自动运行
"""
import os
import time
from config import DATA_DIR

IMAGE_RETENTION_DAYS = 7
IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png"}


def cleanup_old_images(retention_days: int = IMAGE_RETENTION_DAYS) -> int:
    """删除 DATA_DIR 中超过 retention_days 天的图片，返回删除数量"""
    if not os.path.exists(DATA_DIR):
        return 0

    cutoff = time.time() - retention_days * 86400
    deleted = 0

    for fname in os.listdir(DATA_DIR):
        ext = os.path.splitext(fname)[1].lower()
        if ext not in IMAGE_EXTENSIONS:
            continue
        fpath = os.path.join(DATA_DIR, fname)
        try:
            if os.path.getmtime(fpath) < cutoff:
                os.unlink(fpath)
                deleted += 1
        except OSError:
            pass

    if deleted:
        print(f"[cleanup] 删除 {deleted} 张过期图片（>{retention_days}天）")
    return deleted

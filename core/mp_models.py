"""
MediaPipe Tasks 模型文件定位 + 兜底下载。

mediapipe 1.0（Python 3.13 上唯一可用的版本）删除了旧的 `mp.solutions` 接口,
改用 Tasks API,后者需要显式的 `.task` 模型文件。仓库已把两个 lite 模型打包在
`models/` 目录里(随代码一起下发),所以正常情况下**无需联网**。

只有当模型文件缺失时(比如手动精简了仓库),才尝试从 Google 下载 —— 国内网络
可能失败,失败时给出清晰的手动放置指引,而不是抛一个看不懂的异常。
"""
import os
import urllib.request

_MODELS_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "models")

POSE_MODEL = os.path.join(_MODELS_DIR, "pose_landmarker_lite.task")
HAND_MODEL = os.path.join(_MODELS_DIR, "hand_landmarker.task")

_DOWNLOAD_URLS = {
    POSE_MODEL: "https://storage.googleapis.com/mediapipe-models/pose_landmarker/"
                "pose_landmarker_lite/float16/latest/pose_landmarker_lite.task",
    HAND_MODEL: "https://storage.googleapis.com/mediapipe-models/hand_landmarker/"
                "hand_landmarker/float16/latest/hand_landmarker.task",
}


def ensure_model(path: str) -> str:
    """确保模型文件存在,返回其绝对路径。缺失时尝试下载,失败给出可读指引。"""
    if os.path.exists(path) and os.path.getsize(path) > 0:
        return path

    os.makedirs(_MODELS_DIR, exist_ok=True)
    url = _DOWNLOAD_URLS.get(path)
    if not url:
        raise FileNotFoundError(f"未知模型文件: {path}")

    print(f"[mp_models] 模型缺失,尝试下载: {os.path.basename(path)}")
    try:
        urllib.request.urlretrieve(url, path)
        if os.path.getsize(path) == 0:
            raise IOError("下载得到空文件")
        print(f"[mp_models] 下载完成: {path}")
        return path
    except Exception as e:
        # 下载失败(国内网络常见)：删掉半截文件,给出手动放置指引。
        if os.path.exists(path):
            os.remove(path)
        raise FileNotFoundError(
            f"模型文件缺失且自动下载失败({e})。\n"
            f"请在能联网的电脑上下载:\n  {url}\n"
            f"然后放到树莓派的这个位置:\n  {path}"
        )

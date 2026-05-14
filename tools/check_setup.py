"""
环境检查工具 — 验证依赖、摄像头、服务器连通性
运行：python3 tools/check_setup.py
"""
import sys
import os

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

PASS = "\033[92m✓\033[0m"
FAIL = "\033[91m✗\033[0m"
WARN = "\033[93m⚠\033[0m"


def check(name, fn, warn_only=False):
    try:
        ok, detail = fn()
    except Exception as e:
        ok, detail = False, str(e)
    icon = PASS if ok else (WARN if warn_only else FAIL)
    print(f"  {icon} {name}" + (f"  ({detail})" if detail else ""))
    return ok


def check_import(pkg):
    def _():
        __import__(pkg)
        mod = sys.modules[pkg]
        ver = getattr(mod, "__version__", "?")
        return True, ver
    return _


def check_camera():
    import cv2
    cap = cv2.VideoCapture(0)
    ok = cap.isOpened()
    cap.release()
    return ok, "摄像头可用" if ok else "无法打开摄像头"


def check_server():
    import urllib.request
    server = os.environ.get("STUDYLAMP_SERVER", "http://localhost:8000")
    try:
        with urllib.request.urlopen(f"{server}/health", timeout=3) as resp:
            return resp.status == 200, f"{server} 可达"
    except Exception as e:
        return False, f"{server} 不可达: {e}"


def check_data_dir():
    from config import DATA_DIR
    os.makedirs(DATA_DIR, exist_ok=True)
    test_file = os.path.join(DATA_DIR, ".write_test")
    try:
        with open(test_file, "w") as f:
            f.write("ok")
        os.unlink(test_file)
        return True, DATA_DIR
    except Exception as e:
        return False, str(e)


def check_env_var(name):
    def _():
        val = os.environ.get(name, "")
        return bool(val), f"已设置" if val else "未设置（可选）"
    return _


def main():
    print("\n" + "="*50)
    print("StudyLamp 环境检查")
    print("="*50)

    print("\n【Python 依赖】")
    results = []
    results.append(check("rumps", check_import("rumps")))
    results.append(check("opencv-python", check_import("cv2")))
    results.append(check("mediapipe", check_import("mediapipe")))
    results.append(check("numpy", check_import("numpy")))
    results.append(check("fastapi", check_import("fastapi")))
    results.append(check("uvicorn", check_import("uvicorn")))
    results.append(check("sqlalchemy", check_import("sqlalchemy")))
    results.append(check("websockets", check_import("websockets"), warn_only=True))
    results.append(check("paddleocr (可选)", check_import("paddleocr"), warn_only=True))

    print("\n【硬件】")
    results.append(check("摄像头", check_camera))

    print("\n【文件系统】")
    results.append(check("数据目录可写", check_data_dir))

    print("\n【服务器连通性】")
    check("后端服务器", check_server, warn_only=True)

    print("\n【环境变量（可选）】")
    check("GEMINI_API_KEY", check_env_var("GEMINI_API_KEY"), warn_only=True)
    check("WECHAT_APP_ID", check_env_var("WECHAT_APP_ID"), warn_only=True)
    check("STUDYLAMP_DEVICE_ID", check_env_var("STUDYLAMP_DEVICE_ID"), warn_only=True)

    required = results[:10]  # 前 10 项是必须的
    passed = sum(required)
    print(f"\n必要检查：{passed}/{len(required)} 通过")
    if passed == len(required):
        print("✅ 环境就绪，可以运行 python3 main.py")
    else:
        print("❌ 有必要依赖未满足，请先安装：pip install -r requirements.txt")
    print("="*50 + "\n")
    return passed == len(required)


if __name__ == "__main__":
    ok = main()
    sys.exit(0 if ok else 1)

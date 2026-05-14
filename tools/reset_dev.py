"""
开发重置工具 — 清空本地事件文件和服务器数据库
用法：python3 tools/reset_dev.py [--local] [--server] [--all]
"""
import sys
import os
import argparse
import urllib.request
import json

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

SERVER_URL = os.environ.get("STUDYLAMP_SERVER", "http://localhost:8000")
DEVICE_ID = os.environ.get("STUDYLAMP_DEVICE_ID", "mac-dev-001")


def reset_local():
    from config import EVENTS_FILE, DATA_DIR
    deleted = 0
    if os.path.exists(EVENTS_FILE):
        os.unlink(EVENTS_FILE)
        deleted += 1
        print(f"  ✓ 删除 {EVENTS_FILE}")
    # 删除本地图片缓存
    if os.path.exists(DATA_DIR):
        for f in os.listdir(DATA_DIR):
            if f.endswith((".jpg", ".jpeg", ".png")):
                os.unlink(os.path.join(DATA_DIR, f))
                deleted += 1
    print(f"  ✓ 本地重置完成（删除 {deleted} 个文件）")


def reset_server():
    url = f"{SERVER_URL}/api/v1/data?device_id={DEVICE_ID}"
    req = urllib.request.Request(url, method="DELETE")
    try:
        with urllib.request.urlopen(req, timeout=5) as resp:
            data = json.loads(resp.read())
            print(f"  ✓ 服务器重置完成（删除 {data.get('deleted', 0)} 条事件）")
    except Exception as e:
        print(f"  ✗ 服务器重置失败: {e}")


def main():
    global DEVICE_ID
    parser = argparse.ArgumentParser(description="开发重置工具")
    parser.add_argument("--local", action="store_true", help="清空本地事件文件")
    parser.add_argument("--server", action="store_true", help="清空服务器数据库")
    parser.add_argument("--all", action="store_true", help="清空本地 + 服务器")
    parser.add_argument("--device", default=DEVICE_ID, help="设备 ID")
    args = parser.parse_args()

    DEVICE_ID = args.device

    if not any([args.local, args.server, args.all]):
        parser.print_help()
        return

    print(f"重置设备 {DEVICE_ID} 的数据...")

    if args.local or args.all:
        reset_local()
    if args.server or args.all:
        reset_server()

    print("完成。")


if __name__ == "__main__":
    main()

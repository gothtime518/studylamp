"""
模拟学习 session 工具 — 不需要摄像头，写入一次完整学习过程并同步
用法：python3 tools/simulate_session.py [--minutes 45] [--posture-issues 2] [--phone-incidents 1]
"""
import sys
import os
import argparse
import time

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

from datetime import datetime, timezone, timedelta
from core.events import write_event
from core.sync import CloudSync


def simulate(study_minutes: int, posture_issues: int, phone_incidents: int):
    print(f"模拟学习 session：{study_minutes} 分钟，坐姿问题 {posture_issues} 次，玩手机 {phone_incidents} 次")

    now = datetime.now(timezone.utc)

    # session_start
    write_event("session_start", {})
    print("  ✓ session_start")

    # 坐姿问题（均匀分布在学习过程中）
    for i in range(posture_issues):
        write_event("posture_bad", {
            "issues": ["head_forward"],
            "confidence": 0.85,
            "duration": 30,
        })
    if posture_issues:
        print(f"  ✓ posture_bad × {posture_issues}")

    # 玩手机
    for i in range(phone_incidents):
        write_event("activity_change", {
            "from": "studying",
            "to": "using_phone",
            "confidence": 0.91,
        })
        write_event("phone_detected", {"confidence": 0.91})
        write_event("activity_change", {
            "from": "using_phone",
            "to": "studying",
            "confidence": 0.88,
        })
    if phone_incidents:
        print(f"  ✓ phone_detected × {phone_incidents}")

    # session_end（用实际时间差模拟学习时长）
    # 注意：events.py 用当前时间戳，所以 study_minutes 只是模拟数量
    # 真实时长统计依赖 session_start/end 时间差
    write_event("session_end", {})
    print("  ✓ session_end")

    # 同步到服务器
    sync = CloudSync()
    result = sync.sync_now()
    if result["synced"] > 0:
        print(f"  ✓ 已同步 {result['synced']} 条事件到服务器")
    elif result["failed"] > 0:
        print(f"  ⚠ 同步失败（服务器未启动？），事件已保存到本地")
    else:
        print("  ℹ 无待同步事件（可能已同步过）")

    print(f"\n完成。事件文件：{os.path.expanduser('~/Library/Application Support/StudyLamp/events.jsonl')}")


def main():
    parser = argparse.ArgumentParser(description="模拟学习 session")
    parser.add_argument("--minutes", type=int, default=45, help="学习时长（分钟，仅用于显示）")
    parser.add_argument("--posture-issues", type=int, default=2, help="坐姿问题次数")
    parser.add_argument("--phone-incidents", type=int, default=1, help="玩手机次数")
    args = parser.parse_args()
    simulate(args.minutes, args.posture_issues, args.phone_incidents)


if __name__ == "__main__":
    main()

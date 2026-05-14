"""
日报导出工具 — 导出指定日期范围的学习数据为 CSV
用法：python3 tools/export_report.py [--start 2026-04-01] [--end 2026-04-30] [--out report.csv]
"""
import sys
import os
import csv
import argparse
import urllib.request
import json
from datetime import date, timedelta

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

SERVER_URL = os.environ.get("STUDYLAMP_SERVER", "http://localhost:8000")
DEVICE_ID = os.environ.get("STUDYLAMP_DEVICE_ID", "mac-dev-001")


def fetch_daily(day: str) -> dict | None:
    url = f"{SERVER_URL}/api/v1/report/daily/{day}?device_id={DEVICE_ID}"
    try:
        with urllib.request.urlopen(url, timeout=10) as resp:
            return json.loads(resp.read())
    except Exception as e:
        print(f"  [skip] {day}: {e}")
        return None


def date_range(start: str, end: str):
    cur = date.fromisoformat(start)
    end_d = date.fromisoformat(end)
    while cur <= end_d:
        yield cur.isoformat()
        cur += timedelta(days=1)


def main():
    global DEVICE_ID
    parser = argparse.ArgumentParser(description="导出学习日报为 CSV")
    parser.add_argument("--start", default=date.today().replace(day=1).isoformat(),
                        help="开始日期 YYYY-MM-DD（默认本月第一天）")
    parser.add_argument("--end", default=date.today().isoformat(),
                        help="结束日期 YYYY-MM-DD（默认今天）")
    parser.add_argument("--out", default="study_report.csv", help="输出文件名")
    parser.add_argument("--device", default=DEVICE_ID, help="设备 ID")
    args = parser.parse_args()

    DEVICE_ID = args.device

    print(f"导出 {args.start} ~ {args.end} 的学习数据...")
    rows = []
    for day in date_range(args.start, args.end):
        data = fetch_daily(day)
        if data:
            rows.append({
                "日期": data.get("date", day),
                "学习分钟": data.get("study_minutes", 0),
                "坐姿提醒次数": data.get("posture_bad_count", 0),
                "玩手机次数": data.get("phone_count", 0),
                "记录事件数": data.get("event_count", 0),
                "AI建议": data.get("ai_summary", "").replace("\n", " "),
            })

    if not rows:
        print("没有数据可导出")
        return

    out_path = os.path.abspath(args.out)
    with open(out_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)

    print(f"已导出 {len(rows)} 天数据 → {out_path}")

    # 简单统计
    total_min = sum(r["学习分钟"] for r in rows)
    avg_min = total_min / len(rows)
    print(f"  总学习时长：{total_min // 60}小时{total_min % 60}分钟")
    print(f"  日均学习：{avg_min:.0f}分钟")
    print(f"  坐姿提醒总计：{sum(r['坐姿提醒次数'] for r in rows)} 次")
    print(f"  玩手机总计：{sum(r['玩手机次数'] for r in rows)} 次")


if __name__ == "__main__":
    main()

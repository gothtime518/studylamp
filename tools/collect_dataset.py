"""
T1.9 活动分类数据采集脚本
用键盘标注摄像头帧，保存到 dataset/ 目录供后续模型训练

按键说明：
  s — studying（写字/做作业）
  p — using_phone（玩手机）
  i — idle（发呆/看书不动手）
  a — absent（无人）
  q — 退出

运行：python3 tools/collect_dataset.py
"""
import cv2
import os
import time
import json
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from config import CAMERA_INDEX, FRAME_WIDTH, FRAME_HEIGHT

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dataset")
LABELS = {
    ord('s'): "studying",
    ord('p'): "using_phone",
    ord('i'): "idle",
    ord('a'): "absent",
}
LABEL_COLORS = {
    "studying":    (0, 200, 80),
    "using_phone": (0, 60, 220),
    "idle":        (0, 180, 255),
    "absent":      (160, 160, 160),
}


def main():
    os.makedirs(DATASET_DIR, exist_ok=True)
    manifest_path = os.path.join(DATASET_DIR, "manifest.jsonl")

    cap = cv2.VideoCapture(CAMERA_INDEX)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, FRAME_WIDTH)
    cap.set(cv2.CAP_PROP_FRAME_HEIGHT, FRAME_HEIGHT)

    if not cap.isOpened():
        print("无法打开摄像头")
        return

    counts = {label: 0 for label in LABELS.values()}
    current_label = None

    print("数据采集工具启动")
    print("按 s/p/i/a 标注当前帧，按 q 退出")

    while True:
        ret, frame = cap.read()
        if not ret:
            break

        display = frame.copy()

        # 显示当前标签
        if current_label:
            color = LABEL_COLORS.get(current_label, (200, 200, 200))
            cv2.putText(display, f"Label: {current_label}", (12, 36),
                        cv2.FONT_HERSHEY_SIMPLEX, 1.0, color, 2, cv2.LINE_AA)

        # 显示各类别计数
        y = 70
        for label, count in counts.items():
            cv2.putText(display, f"{label}: {count}", (12, y),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1, cv2.LINE_AA)
            y += 22

        cv2.putText(display, "s=studying p=phone i=idle a=absent q=quit",
                    (12, FRAME_HEIGHT - 12),
                    cv2.FONT_HERSHEY_SIMPLEX, 0.45, (150, 150, 150), 1, cv2.LINE_AA)

        cv2.imshow("StudyLamp Dataset Collector", display)
        key = cv2.waitKey(30)

        if key == ord('q') or key == 27:
            break

        if key in LABELS:
            label = LABELS[key]
            current_label = label
            ts = int(time.time() * 1000)
            filename = f"{label}_{ts}.jpg"
            filepath = os.path.join(DATASET_DIR, filename)
            cv2.imwrite(filepath, frame)
            counts[label] += 1

            # 写入 manifest
            with open(manifest_path, "a", encoding="utf-8") as f:
                f.write(json.dumps({
                    "file": filename,
                    "label": label,
                    "timestamp": ts,
                }, ensure_ascii=False) + "\n")

            print(f"  保存 {filename} [{label}] 累计 {counts[label]} 张")

    cap.release()
    cv2.destroyAllWindows()

    total = sum(counts.values())
    print(f"\n采集完成，共 {total} 张")
    for label, count in counts.items():
        print(f"  {label}: {count} 张")
    print(f"数据保存在 {DATASET_DIR}/")


if __name__ == "__main__":
    main()

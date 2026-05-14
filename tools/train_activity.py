"""
T1.9 活动分类模型训练脚本
读取 dataset/manifest.jsonl，用 MediaPipe Hands 提取特征，训练 sklearn 分类器

用法：
  1. 先用 tools/collect_dataset.py 采集数据
  2. python3 tools/train_activity.py
  3. 生成 dataset/activity_model.pkl
"""
import sys
import os
import json
import pickle
import numpy as np

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

DATASET_DIR = os.path.join(os.path.dirname(os.path.dirname(__file__)), "dataset")
MANIFEST = os.path.join(DATASET_DIR, "manifest.jsonl")
MODEL_OUT = os.path.join(DATASET_DIR, "activity_model.pkl")
LABEL_MAP = {"studying": 0, "using_phone": 1, "idle": 2, "absent": 3}
LABEL_INV = {v: k for k, v in LABEL_MAP.items()}


def extract_features(image_path: str) -> np.ndarray | None:
    """用 MediaPipe Hands 提取 21 个手部关键点 (x,y,z) = 63 维特征"""
    import cv2
    import mediapipe as mp

    mp_hands = mp.solutions.hands
    hands = mp_hands.Hands(
        max_num_hands=2,
        min_detection_confidence=0.5,
        min_tracking_confidence=0.5,
        model_complexity=0,
    )

    img = cv2.imread(image_path)
    if img is None:
        return None
    rgb = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    result = hands.process(rgb)
    hands.close()

    if not result.multi_hand_landmarks:
        # 无手部 → 全零特征（代表 idle/absent）
        return np.zeros(63)

    # 取第一只手的 21 个关键点
    lm = result.multi_hand_landmarks[0].landmark
    return np.array([[p.x, p.y, p.z] for p in lm]).flatten()


def main():
    if not os.path.exists(MANIFEST):
        print(f"找不到 {MANIFEST}，请先运行 tools/collect_dataset.py 采集数据")
        sys.exit(1)

    with open(MANIFEST, "r", encoding="utf-8") as f:
        entries = [json.loads(l) for l in f if l.strip()]

    if len(entries) < 20:
        print(f"数据量不足（{len(entries)} 条），建议每类至少 50 张")

    X, y = [], []
    skipped = 0
    for entry in entries:
        path = os.path.join(DATASET_DIR, entry["file"])
        label = entry["label"]
        if label not in LABEL_MAP:
            continue
        feat = extract_features(path)
        if feat is None:
            skipped += 1
            continue
        X.append(feat)
        y.append(LABEL_MAP[label])

    print(f"有效样本：{len(X)}，跳过：{skipped}")
    if len(X) < 10:
        print("样本太少，无法训练")
        sys.exit(1)

    X = np.array(X)
    y = np.array(y)

    from sklearn.ensemble import RandomForestClassifier
    from sklearn.model_selection import cross_val_score
    from sklearn.preprocessing import StandardScaler

    scaler = StandardScaler()
    X_scaled = scaler.fit_transform(X)

    clf = RandomForestClassifier(n_estimators=100, random_state=42)
    scores = cross_val_score(clf, X_scaled, y, cv=min(5, len(X) // 4), scoring="accuracy")
    print(f"交叉验证准确率：{scores.mean():.2%} ± {scores.std():.2%}")

    clf.fit(X_scaled, y)

    model = {"clf": clf, "scaler": scaler, "label_map": LABEL_MAP, "label_inv": LABEL_INV}
    with open(MODEL_OUT, "wb") as f:
        pickle.dump(model, f)

    print(f"模型已保存到 {MODEL_OUT}")

    # 各类别样本数
    from collections import Counter
    counts = Counter(LABEL_INV[l] for l in y)
    for label, count in sorted(counts.items()):
        print(f"  {label}: {count} 张")


if __name__ == "__main__":
    main()

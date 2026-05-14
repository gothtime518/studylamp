"""积分计算规则"""

POINTS_PER_30MIN = 10       # 每 30 分钟学习得 10 分
POINTS_GOOD_POSTURE = 5     # 当天坐姿提醒 0 次额外奖励
POINTS_NO_PHONE = 5         # 当天玩手机 0 次额外奖励
POINTS_STREAK_BONUS = 20    # 连续学习 3 天以上额外奖励

BADGES = [
    {"id": "first_session",  "name": "初次启动",   "icon": "🚀", "condition": "total_days >= 1"},
    {"id": "focus_30",       "name": "专注 30 分",  "icon": "⏱️", "condition": "study_minutes >= 30"},
    {"id": "focus_60",       "name": "专注达人",    "icon": "🎯", "condition": "study_minutes >= 60"},
    {"id": "posture_perfect","name": "坐姿标准",    "icon": "🧘", "condition": "posture_bad_count == 0"},
    {"id": "no_phone",       "name": "专心学习",    "icon": "📵", "condition": "phone_count == 0"},
    {"id": "streak_3",       "name": "三天连续",    "icon": "🔥", "condition": "streak >= 3"},
    {"id": "streak_7",       "name": "一周坚持",    "icon": "🏆", "condition": "streak >= 7"},
]


def calc_daily_points(study_minutes: int, posture_bad_count: int,
                      phone_count: int, streak: int) -> list:
    """返回当天积分明细列表"""
    ledger = []

    # 学习时长积分
    time_pts = (study_minutes // 30) * POINTS_PER_30MIN
    if time_pts > 0:
        ledger.append({"points": time_pts, "reason": "study_time",
                       "label": f"学习 {study_minutes} 分钟"})

    # 坐姿良好奖励
    if posture_bad_count == 0 and study_minutes > 0:
        ledger.append({"points": POINTS_GOOD_POSTURE, "reason": "good_posture",
                       "label": "坐姿全程良好"})

    # 不玩手机奖励
    if phone_count == 0 and study_minutes > 0:
        ledger.append({"points": POINTS_NO_PHONE, "reason": "no_phone",
                       "label": "专心不玩手机"})

    # 连续学习奖励
    if streak >= 3:
        ledger.append({"points": POINTS_STREAK_BONUS, "reason": "streak",
                       "label": f"连续学习 {streak} 天"})

    return ledger


def calc_badges(stats: dict) -> list:
    """根据累计统计返回已解锁徽章列表"""
    unlocked = []
    for badge in BADGES:
        try:
            if eval(badge["condition"], {}, stats):
                unlocked.append({k: v for k, v in badge.items() if k != "condition"})
        except Exception:
            pass
    return unlocked

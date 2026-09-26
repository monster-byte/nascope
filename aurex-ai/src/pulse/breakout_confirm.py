
"""
AUREX Pulse - Breakout Confirmation (بوابة 3 من استراتيجية السكالب الشخصية)
يفحص هل السعر كسر VAH أو VAL فعلاً بشكل مؤكد (استمرارية بعد الكسر)، أو كان
كسر كاذب (Fakeout) رجع يصحّح للداخل — محصور بساعات جلسة نيويورك الرسمية
(9:30ص - 4:00م بتوقيت نيويورك) بس، حسب استراتيجية المستخدم بالضبط:
"تأكيدات بالكسر بجلسة نيويورك، مع خطة لتصحيح السوق (مو أي كسر يُعتبر صحيح)".

منطق التأكيد:
- نبحث عن آخر لحظة عبور فعلي لمستوى VAH (كسر صاعد) أو VAL (كسر هابط).
- بعد لحظة الكسر، نراقب الشموع التالية: لو أي وحدة منهم رجعت وأغلقت داخل
  المستوى تاني = كسر كاذب (Fakeout / تصحيح)، مرفوض.
- لو استمر السعر خارج المستوى لعدد كافٍ من الشموع (CONFIRMATION_CANDLES)
  بدون أي رجوع = كسر مؤكد.
- لو لسا العدد ما اكتمل (بس ما رجع للداخل لحد الآن) = "قيد المراقبة".

⚠️ هذا العامل استشاري ضمن محرك Pulse — لا يدخل بحساب confirmation_score
الرسمي بالمحرك الأساسي (AUREX AI) بأي شكل.
"""

from datetime import time

from .volume_profile import group_by_session

NY_SESSION_START = time(9, 30)
NY_SESSION_END = time(16, 0)

CONFIRMATION_CANDLES = 3   # 3 شموع × 5 دقايق = 15 دقيقة استمرارية بعد الكسر عشان يُعتبر مؤكد
LOOKBACK_CANDLES = 24      # نفحص آخر ساعتين بس بحثاً عن كسر حديث (24 × 5 دقايق)


def is_ny_session(dt) -> bool:
    """يتحقق هل الوقت داخل جلسة نيويورك الرسمية (9:30ص - 4:00م)."""
    t = dt.time()
    return NY_SESSION_START <= t <= NY_SESSION_END


def detect_breakout(all_candles: list, val: float, vah: float) -> dict:
    """يفحص آخر كسر لمستوى VAH/VAL خلال جلسة نيويورك الحالية، ويتحقق
    هل هو كسر مؤكد (استمرارية) أو كسر كاذب (رجع يصحّح) أو لسا قيد المراقبة."""
    if val is None or vah is None:
        return {"status": "no_levels", "in_ny_session": False}

    sessions = group_by_session(all_candles)
    if not sessions:
        return {"status": "no_session_data", "in_ny_session": False}

    current_key = sorted(sessions.keys())[-1]
    current_session = sessions[current_key]
    if not current_session:
        return {"status": "no_session_data", "in_ny_session": False}

    now_dt = current_session[-1][0]
    in_session = is_ny_session(now_dt)

    if not in_session:
        return {"status": "outside_ny_session", "in_ny_session": False}

    ny_candles = [(dt, c) for dt, c in current_session if is_ny_session(dt)]
    recent = ny_candles[-LOOKBACK_CANDLES:] if len(ny_candles) > LOOKBACK_CANDLES else ny_candles

    if len(recent) < 2:
        return {"status": "insufficient_candles", "in_ny_session": True}

    breakout_idx = None
    breakout_level = None
    breakout_direction = None

    for i in range(1, len(recent)):
        prev_close = recent[i - 1][1]["close"]
        cur_close = recent[i][1]["close"]

        if prev_close <= vah < cur_close:
            breakout_idx, breakout_level, breakout_direction = i, vah, "UP"
        elif prev_close >= val > cur_close:
            breakout_idx, breakout_level, breakout_direction = i, val, "DOWN"

    if breakout_idx is None:
        return {"status": "no_breakout", "in_ny_session": True}

    breakout_time = recent[breakout_idx][0]
    candles_since_breakout = recent[breakout_idx:]

    failed = False
    for dt, c in candles_since_breakout[1:]:
        if breakout_direction == "UP" and c["close"] <= breakout_level:
            failed = True
            break
        if breakout_direction == "DOWN" and c["close"] >= breakout_level:
            failed = True
            break

    candles_confirmed = len(candles_since_breakout) - 1
    minutes_since = round((now_dt - breakout_time).total_seconds() / 60, 1)

    if failed:
        status = "failed_fakeout"
    elif candles_confirmed >= CONFIRMATION_CANDLES:
        status = "confirmed_up" if breakout_direction == "UP" else "confirmed_down"
    else:
        status = "pending_confirmation"

    return {
        "status": status,
        "in_ny_session": True,
        "level_broken": "VAH" if breakout_direction == "UP" else "VAL",
        "level_price": round(breakout_level, 2),
        "breakout_time": breakout_time.isoformat(),
        "minutes_since_breakout": minutes_since,
        "candles_confirmed_so_far": candles_confirmed,
        "candles_required": CONFIRMATION_CANDLES,
    }
"""
AUREX Pulse - Developing Volume Profile
يحسب POC (Point of Control) وValue Area (VAH/VAL) لجلسة عقود NQ الحالية
"وهي قيد التطوّر" (Developing) بالاعتماد على شموع 5 دقايق الموجودة أصلاً
بملف snapshot الأسعار — بدون أي مصدر بيانات إضافي أو اشتراك مدفوع.

⚠️ قيد تقني موثّق بوضوح: لا نملك بيانات Tick (صفقة بصفقة)، فقط شموع OHLCV
كل 5 دقايق. نفترض أن حجم كل شمعة موزّع بالتساوي على نطاقها السعري
(High→Low) — تقريب معياري معروف بالصناعة عند غياب بيانات Tick، وليس
دقة مطلقة. كلما كان نطاق الشمعة أوسع (تقلب عنيف)، كلما كان التقريب أخشن.

حدود جلسة "اليوم": نعتمد يوم تداول عقود CME (يبدأ 6:00م بتوقيت نيويورك)
كمرجع، بدل منتصف الليل بالتقويم العادي، لأن عقود NQ تتداول شبه 24 ساعة.
"""

import math
from datetime import datetime, timedelta

BIN_SIZE_DEFAULT = 25.0        # حجم الصندوق السعري بنقاط NQ (قابل للتعديل)
VALUE_AREA_PCT = 0.70          # النسبة القياسية لـValue Area (70% من الحجم)
SESSION_CUTOFF_HOUR = 18       # بداية يوم تداول CME: 6:00م بتوقيت نيويورك
NEAR_TOLERANCE_POINTS = 10.0   # هامش اعتبار السعر "قريب" من مستوى معيّن


def _parse(ts: str) -> datetime:
    return datetime.fromisoformat(ts)


def _session_key(dt: datetime) -> datetime:
    """يرجع "بداية الجلسة" (6:00م نيويورك) اللي تنتمي لها هذه الشمعة."""
    cutoff = dt.replace(hour=SESSION_CUTOFF_HOUR, minute=0, second=0, microsecond=0)
    return cutoff if dt.hour >= SESSION_CUTOFF_HOUR else cutoff - timedelta(days=1)


def group_by_session(candles: list) -> dict:
    """يجمّع الشموع حسب جلسة يوم التداول اللي تنتمي لها كل وحدة."""
    parsed = sorted(((_parse(c["time"]), c) for c in candles), key=lambda x: x[0])
    sessions = {}
    for dt, c in parsed:
        key = _session_key(dt)
        sessions.setdefault(key, []).append((dt, c))
    return sessions


def _bin_floor(price: float, bin_size: float) -> float:
    return math.floor(price / bin_size) * bin_size


def build_volume_profile(session_candles: list, bin_size: float = BIN_SIZE_DEFAULT) -> dict:
    """يوزّع حجم كل شمعة بالتساوي على الصناديق السعرية اللي يتقاطع معها نطاقها."""
    volume_by_bin = {}
    for _, c in session_candles:
        low, high, vol = c["low"], c["high"], c.get("volume", 0)
        if vol <= 0 or high < low:
            continue
        bin_low = _bin_floor(low, bin_size)
        bin_high = _bin_floor(high, bin_size)
        bins_touched = int(round((bin_high - bin_low) / bin_size)) + 1
        vol_per_bin = vol / bins_touched
        b = bin_low
        for _ in range(bins_touched):
            volume_by_bin[b] = volume_by_bin.get(b, 0.0) + vol_per_bin
            b += bin_size
    return volume_by_bin


def compute_poc_value_area(volume_by_bin: dict, bin_size: float = BIN_SIZE_DEFAULT,
                            value_area_pct: float = VALUE_AREA_PCT):
    """يحسب POC وVAL وVAH من توزيع الحجم على الصناديق."""
    if not volume_by_bin:
        return None, None, None

    total_volume = sum(volume_by_bin.values())
    sorted_bins = sorted(volume_by_bin.keys())
    poc_bin = max(volume_by_bin, key=volume_by_bin.get)

    low_idx = high_idx = sorted_bins.index(poc_bin)
    included_volume = volume_by_bin[poc_bin]
    target = value_area_pct * total_volume

    while included_volume < target:
        can_go_up = high_idx + 1 < len(sorted_bins)
        can_go_down = low_idx - 1 >= 0
        if not can_go_up and not can_go_down:
            break
        vol_up = volume_by_bin[sorted_bins[high_idx + 1]] if can_go_up else -1
        vol_down = volume_by_bin[sorted_bins[low_idx - 1]] if can_go_down else -1
        if vol_up >= vol_down:
            high_idx += 1
            included_volume += vol_up
        else:
            low_idx -= 1
            included_volume += vol_down

    poc = round(poc_bin + bin_size / 2, 2)          # منتصف صندوق الـPOC
    val = round(sorted_bins[low_idx], 2)              # الحد الأدنى لمنطقة القيمة
    vah = round(sorted_bins[high_idx] + bin_size, 2)  # الحد الأعلى لمنطقة القيمة
    return poc, val, vah


def compute_relative_volume(all_candles: list) -> dict:
    """يقارن الحجم التراكمي للجلسة الحالية لحد الآن بمتوسط نفس النقطة الزمنية
    بالجلسات السابقة المتوفرة (من نفس نافذة الـ5 أيام، بدون طلب بيانات إضافي)."""
    sessions = group_by_session(all_candles)
    if not sessions:
        return {"relative_volume_pct": None, "note": "لا توجد بيانات كافية"}

    session_keys = sorted(sessions.keys())
    current_key = session_keys[-1]
    current_session = sessions[current_key]
    now_dt = current_session[-1][0]
    elapsed = now_dt - current_key
    current_cum_volume = sum(c.get("volume", 0) for _, c in current_session)

    prior_keys = session_keys[:-1]
    if not prior_keys:
        return {
            "relative_volume_pct": None,
            "sessions_compared": 0,
            "note": "لا توجد جلسات سابقة كافية للمقارنة بعد (أول جلسة بالنافذة الزمنية المتوفرة)",
        }

    prior_cum_volumes = []
    for k in prior_keys:
        cum = sum(c.get("volume", 0) for dt, c in sessions[k] if dt - k <= elapsed)
        prior_cum_volumes.append(cum)

    avg_prior = sum(prior_cum_volumes) / len(prior_cum_volumes) if prior_cum_volumes else 0
    if avg_prior <= 0:
        return {
            "relative_volume_pct": None,
            "sessions_compared": len(prior_keys),
            "note": "متوسط حجم الجلسات السابقة غير متوفر (صفر)",
        }

    pct = round((current_cum_volume / avg_prior) * 100, 1)
    return {"relative_volume_pct": pct, "sessions_compared": len(prior_keys)}


def classify_price_location(current_price: float, poc: float, val: float, vah: float,
                             tolerance: float = NEAR_TOLERANCE_POINTS) -> str:
    if poc is None:
        return "UNKNOWN"
    if abs(current_price - vah) <= tolerance:
        return "NEAR_VAH"
    if abs(current_price - val) <= tolerance:
        return "NEAR_VAL"
    if abs(current_price - poc) <= tolerance:
        return "NEAR_POC"
    if current_price > vah:
        return "ABOVE_VALUE_AREA"
    if current_price < val:
        return "BELOW_VALUE_AREA"
    return "INSIDE_VALUE_AREA"


def compute_volume_profile(price_snapshot: dict, symbol_key: str = "NASDAQ_FUTURES",
                            bin_size: float = BIN_SIZE_DEFAULT) -> dict:
    """نقطة الدخول الرئيسية: تاخد نفس snapshot الأسعار المستخدم بالمحرك الأساسي،
    وترجع Developing POC/VAH/VAL + الحجم النسبي + موقع السعر الحالي."""
    symbol_data = price_snapshot.get(symbol_key) if price_snapshot else None
    if not symbol_data or not symbol_data.get("candles"):
        return {
            "error": f"لا توجد بيانات شموع لـ {symbol_key}",
            "poc": None, "val": None, "vah": None,
            "price_location": "UNKNOWN",
            "relative_volume_pct": None,
        }

    all_candles = symbol_data["candles"]
    sessions = group_by_session(all_candles)
    if not sessions:
        return {
            "error": "تعذّر تحديد جلسة اليوم الحالي",
            "poc": None, "val": None, "vah": None,
            "price_location": "UNKNOWN",
            "relative_volume_pct": None,
        }

    current_key = sorted(sessions.keys())[-1]
    current_session = sessions[current_key]

    volume_by_bin = build_volume_profile(current_session, bin_size)
    poc, val, vah = compute_poc_value_area(volume_by_bin, bin_size)

    current_price = float(current_session[-1][1]["close"])
    location = classify_price_location(current_price, poc, val, vah)
    rel_volume = compute_relative_volume(all_candles)

    return {
        "session_start": current_key.isoformat(),
        "current_price": round(current_price, 2),
        "poc": poc,
        "val": val,
        "vah": vah,
        "price_location": location,
        "bin_size_points": bin_size,
        "value_area_pct_target": VALUE_AREA_PCT,
        "candles_in_session": len(current_session),
        **rel_volume,
        "methodology_note": (
            "POC/VAH/VAL مبنية بتقريب توزيع متساوٍ للحجم على نطاق كل شمعة 5 دقايق "
            "(لا تتوفر بيانات Tick). الدقة تقل مع اتساع نطاق الشمعة."
        ),
    }

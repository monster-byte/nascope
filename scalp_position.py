"""
AUREX Pulse - Scalp Position (Entry / Stop Loss / Take Profit للسكالب)
يحسب نقاط الدخول/الوقف/الهدف لإشارة سكالب فعلية (SCALP_BULLISH/BEARISH)،
بالاعتماد على مستوى الكسر نفسه (VAH للشراء، VAL للبيع) كنقطة إبطال منطقية
— نفس المستوى اللي breakout_confirm.py يعتبر تجاوزه عكسياً "فشل الكسر"
أصلاً، فاستخدامه كوقف خسارة متّسق 100% مع منطق البوابة 3.

Risk:Reward بنفس مضاعفات position_sizing.py الأساسي (1.5 / 3.0) للتناسق،
بس المسافات هنا مبنية على نقاط AMT هيكلية فعلية (مو % ثابتة من السعر) —
مناسبة لأفق سكالب قصير (دقايق)، مو صفقة أيام.

⚠️ استشاري بحت، لا ربط حقيقي بأي وسيط أو تنفيذ فعلي للصفقة.
"""

TP1_RR_MULTIPLE = 1.5
TP2_RR_MULTIPLE = 3.0
MIN_STOP_DISTANCE_POINTS = 10.0  # حد أدنى لمسافة الوقف، تجنّباً لوقف قريب جداً بسبب ضجيج عادي


def compute_scalp_position(fusion_result: dict, vp: dict) -> dict:
    final_signal = fusion_result.get("final_signal") if fusion_result else None
    if final_signal not in ("SCALP_BULLISH", "SCALP_BEARISH"):
        return {"available": False, "reason": "no_active_scalp_signal"}

    entry = vp.get("current_price") if vp else None
    vah = vp.get("vah") if vp else None
    val = vp.get("val") if vp else None
    if entry is None or vah is None or val is None:
        return {"available": False, "reason": "missing_amt_levels"}

    if final_signal == "SCALP_BULLISH":
        stop = vah
        stop_distance = entry - stop
        if stop_distance < MIN_STOP_DISTANCE_POINTS:
            stop = entry - MIN_STOP_DISTANCE_POINTS
            stop_distance = MIN_STOP_DISTANCE_POINTS
        tp1 = entry + stop_distance * TP1_RR_MULTIPLE
        tp2 = entry + stop_distance * TP2_RR_MULTIPLE
    else:  # SCALP_BEARISH
        stop = val
        stop_distance = stop - entry
        if stop_distance < MIN_STOP_DISTANCE_POINTS:
            stop = entry + MIN_STOP_DISTANCE_POINTS
            stop_distance = MIN_STOP_DISTANCE_POINTS
        tp1 = entry - stop_distance * TP1_RR_MULTIPLE
        tp2 = entry - stop_distance * TP2_RR_MULTIPLE

    return {
        "available": True,
        "direction": "LONG" if final_signal == "SCALP_BULLISH" else "SHORT",
        "entry": round(entry, 2),
        "stop_loss": round(stop, 2),
        "take_profit_1": round(tp1, 2),
        "take_profit_2": round(tp2, 2),
        "stop_distance_points": round(stop_distance, 2),
        "risk_reward_tp1": TP1_RR_MULTIPLE,
        "risk_reward_tp2": TP2_RR_MULTIPLE,
        "expected_holding_time": "2-10 دقايق تقريباً (حسب سرعة وصول الهدف)",
    }

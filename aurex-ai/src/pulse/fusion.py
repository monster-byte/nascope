"""
AUREX Pulse - Fusion (خط أنابيب متسلسل، مطابق لاستراتيجية السكالب الشخصية بالضبط)

الترتيب: أخبار/سياق → AMT (Volume Profile) → تأكيد الكسر (جلسة نيويورك) → VXN
بوابات متسلسلة، مو "عدّ توافق" — كل بوابة لازم تعدّي قبل ما توصل للي بعدها،
وبس لو الأربعة عدّوا بنفس الاتجاه، يصير عندك "إشارة سكالب" حقيقية.

بوابة 1 تنسحب تلقائياً (auto-pass) بالأيام الهادئة (direction=NEUTRAL من
context_gate.py) — نعتمد AMT + الكسر + VXN لحالهم بهالحالة، بالضبط متل
استراتيجية المستخدم الأصلية.

⚠️ هذا الملف استشاري بحت — ما يكتب على signal_snapshot.json ولا يدخل
بحساب confirmation_score الرسمي بالمحرك الأساسي (AUREX AI) بأي شكل.
"""

STRUCTURAL_LOCATIONS = {"NEAR_VAH", "NEAR_VAL", "NEAR_POC", "ABOVE_VALUE_AREA", "BELOW_VALUE_AREA"}

_LOCATION_LABEL_AR = {
    "NEAR_POC": "نقطة التحكم (POC)",
    "NEAR_VAH": "الحد الأعلى لمنطقة القيمة (VAH)",
    "NEAR_VAL": "الحد الأدنى لمنطقة القيمة (VAL)",
    "ABOVE_VALUE_AREA": "أعلى منطقة القيمة",
    "BELOW_VALUE_AREA": "أسفل منطقة القيمة",
    "INSIDE_VALUE_AREA": "داخل منطقة القيمة (منطقة توازن)",
    "UNKNOWN": "غير محدد (بيانات غير كافية)",
}

_BREAKOUT_STATUS_LABEL_AR = {
    "confirmed_up": "كسر صاعد مؤكد",
    "confirmed_down": "كسر هابط مؤكد",
    "failed_fakeout": "كسر كاذب (رفضناه)",
    "pending_confirmation": "كسر حديث، قيد المراقبة",
    "no_breakout": "لا يوجد كسر حالياً",
    "outside_ny_session": "خارج جلسة نيويورك",
    "no_session_data": "لا توجد بيانات جلسة كافية",
    "no_levels": "مستويات AMT غير متوفرة",
    "insufficient_candles": "شموع غير كافية",
}


def _gate2_amt_location(vp: dict) -> dict:
    """بوابة 2: هل السعر عند مستوى AMT مهم (POC/VAH/VAL أو خارج منطقة القيمة)؟"""
    location = vp.get("price_location", "UNKNOWN") if vp else "UNKNOWN"
    return {"passed": location in STRUCTURAL_LOCATIONS, "location": location}


def _gate3_breakout(breakout: dict) -> dict:
    """بوابة 3: كسر مؤكد فعلاً (مو كاذب، مو قيد المراقبة، مو خارج الجلسة)."""
    status = breakout.get("status") if breakout else None
    direction = None
    if status == "confirmed_up":
        direction = "BULLISH"
    elif status == "confirmed_down":
        direction = "BEARISH"
    return {"passed": direction is not None, "status": status, "direction": direction}


def _gate1_context(daily_context: dict, breakout_direction: str) -> dict:
    """بوابة 1: هل الانحياز اليومي (AUREX AI) يوافق اتجاه الكسر؟
    لو السياق "هادئ" (NEUTRAL)، البوابة تنسحب تلقائياً — نعتمد باقي
    البوابات لحالها (بالضبط متل استراتيجية المستخدم بالأيام الهادئة)."""
    direction = daily_context.get("direction", "UNKNOWN") if daily_context else "UNKNOWN"
    if breakout_direction is None:
        return {"passed": None, "direction": direction, "source": daily_context.get("source") if daily_context else None}
    if direction == "NEUTRAL":
        return {
            "passed": True,
            "direction": direction,
            "source": daily_context.get("source") if daily_context else None,
            "note": "يوم هادئ — AMT يقرر لحاله",
        }
    return {
        "passed": direction == breakout_direction,
        "direction": direction,
        "source": daily_context.get("source") if daily_context else None,
    }


def _gate4_vxn(vxn_factor: dict, breakout_direction: str) -> dict:
    """بوابة 4: VXN ما يعارض اتجاه الكسر. خوف مرتفع (status=red) يعارض
    الكسور الصاعدة تحديداً (يقوّض الاستمرارية)، ولا يعارض الكسور الهابطة
    أبداً بهذا النموذج (الخوف المرتفع أصلاً إشارة هبوطية الطبيعة)."""
    status = vxn_factor.get("status") if vxn_factor else None
    if breakout_direction is None:
        return {"passed": None, "status": status}
    if breakout_direction == "BULLISH":
        return {"passed": status != "red", "status": status}
    return {"passed": True, "status": status}


def _build_reason_ar(gates: dict, final_signal: str, breakout: dict) -> str:
    g1, g2, g3, g4 = gates["gate1_context"], gates["gate2_amt_location"], gates["gate3_breakout"], gates["gate4_vxn"]
    breakout_label = _BREAKOUT_STATUS_LABEL_AR.get(g3.get("status"), g3.get("status") or "غير معروف")
    location_label = _LOCATION_LABEL_AR.get(g2.get("location"), g2.get("location"))

    if final_signal in ("SCALP_BULLISH", "SCALP_BEARISH"):
        direction_ar = "صاعد" if final_signal == "SCALP_BULLISH" else "هابط"
        context_note = " (يوم هادئ، AMT قرر لحاله)" if g1.get("direction") == "NEUTRAL" else ""
        return (
            f"✅ الأربع بوابات عدّت بنفس الاتجاه ({direction_ar}){context_note}: "
            f"السعر عند {location_label}، {breakout_label}، "
            f"ومؤشر الخوف (VXN) ما يعارض. إشارة سكالب مكتملة."
        )

    if g3.get("direction") is None:
        return f"لا توجد إشارة كسر مؤكدة حالياً ({breakout_label}) — النظام لسا بمرحلة المراقبة."

    failed = []
    if g1.get("passed") is False:
        failed.append("السياق اليومي (AUREX AI) يعارض اتجاه الكسر")
    if g2.get("passed") is False:
        failed.append(f"السعر مو عند مستوى AMT مهم حالياً ({location_label})")
    if g4.get("passed") is False:
        failed.append("مؤشر الخوف (VXN) مرتفع ويعارض استمرارية الكسر الصاعد")

    reason = f"⚠️ في كسر ({breakout_label}) بس ما اكتملت كل البوابات: " + "، ".join(failed) if failed else \
        f"⚠️ في كسر ({breakout_label}) وباقي البوابات بانتظار التأكيد."
    return reason


def fuse(vp: dict, daily_context: dict, breakout: dict, vxn_factor: dict) -> dict:
    """نقطة الدخول الرئيسية: خط الأنابيب المتسلسل الكامل (4 بوابات)."""
    gate3 = _gate3_breakout(breakout)
    gate2 = _gate2_amt_location(vp)
    gate1 = _gate1_context(daily_context, gate3["direction"])
    gate4 = _gate4_vxn(vxn_factor, gate3["direction"])

    gates = {
        "gate1_context": gate1,
        "gate2_amt_location": gate2,
        "gate3_breakout": gate3,
        "gate4_vxn": gate4,
    }

    all_passed = (
        gate3["direction"] is not None
        and gate1["passed"] is True
        and gate2["passed"] is True
        and gate4["passed"] is True
    )

    if all_passed:
        final_signal = "SCALP_BULLISH" if gate3["direction"] == "BULLISH" else "SCALP_BEARISH"
    elif gate3["direction"] is not None:
        final_signal = "SETUP_INCOMPLETE"
    else:
        final_signal = "NO_SETUP"

    return {
        "final_signal": final_signal,
        "breakout_direction": gate3["direction"],
        "gates": gates,
        "reason": _build_reason_ar(gates, final_signal, breakout),
        "is_advisory_only": True,
    }

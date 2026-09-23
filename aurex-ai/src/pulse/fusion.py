"""
AUREX Pulse - Fusion
يدمج Volume Profile (وين السعر هيكلياً) + Catalyst Watcher (هل في شي جديد صار هلق)
+ VXN (مؤشر الخوف اللحظي) بمنطق واحد واضح، ويرجع تنبيه استشاري واحد.

مؤشر VXN هون يُعاد حسابه كل 5 دقايق مع كل تشغيل لمحرك Pulse (بنفس دورة
volume_profile وcatalyst_watcher تماماً) — نفس دالة compute_vxn_factor
المستخدمة أصلاً بالمحرك الرئيسي (AUREX AI)، بدون أي تكرار كود، وبدون أي
مصدر بيانات إضافي (نفس snapshot_1D.json المحدَّث لحظياً).

⚠️ قاعدة معمارية أساسية: هذا الملف "استشاري" بحت — ما يكتب على
signal_snapshot.json ولا يدخل بحساب confirmation_score الرسمي بأي شكل.
الهدف يعطي متداول فريم 5 دقايق سياق إضافي يشوفه بعينه ويقرر هو، مو قرار آلي.
"""

# مستويات هيكلية تعتبر "مهمة" — لو السعر عندها + كاتاليست طازج = انتباه أعلى
STRUCTURAL_LOCATIONS = {"NEAR_VAH", "NEAR_VAL", "NEAR_POC", "ABOVE_VALUE_AREA", "BELOW_VALUE_AREA"}

HIGH_REL_VOLUME_THRESHOLD = 150.0
MODERATE_REL_VOLUME_THRESHOLD = 130.0


def _compute_direction(catalyst: dict, vxn_factor: dict = None) -> str:
    """يستخرج انحياز الميل (صعودي/هبوطي/محايد) من كاتاليست الأخبار/التقويم
    + مؤشر الخوف VXN (خوف مرتفع = صوت هبوطي إضافي)."""
    leans = []

    if catalyst and catalyst.get("detected"):
        calendar_result = catalyst.get("calendar", {})
        if calendar_result.get("detected"):
            for ev in calendar_result.get("events", []):
                surprise = ev.get("surprise")
                if surprise == "BETTER_THAN_FORECAST":
                    leans.append("BULLISH")
                elif surprise == "WORSE_THAN_FORECAST":
                    leans.append("BEARISH")

        news_result = catalyst.get("news", {})
        if news_result.get("detected"):
            for h in news_result.get("headlines", []):
                sentiment = h.get("sentiment")
                if sentiment == "Positive":
                    leans.append("BULLISH")
                elif sentiment == "Negative":
                    leans.append("BEARISH")

    # VXN مرتفع نسبياً (status=red) = خوف/توتر متصاعد = صوت هبوطي إضافي
    # (VXN منخفض ما بيضاف كصوت صعودي — الهدوء وحده مو دليل صعود، تصميم متحفّظ مقصود)
    if vxn_factor and vxn_factor.get("status") == "red":
        leans.append("BEARISH")

    if not leans:
        return "NEUTRAL"

    bullish_count = leans.count("BULLISH")
    bearish_count = leans.count("BEARISH")
    if bullish_count > bearish_count:
        return "BULLISH_LEAN"
    if bearish_count > bullish_count:
        return "BEARISH_LEAN"
    return "MIXED"


def _build_reason(vp: dict, catalyst: dict, vxn_factor: dict, direction: str) -> str:
    parts = []

    location = vp.get("price_location", "UNKNOWN") if vp else "UNKNOWN"
    location_ar = {
        "NEAR_VAH": "قريب من الحد الأعلى لمنطقة القيمة (VAH)",
        "NEAR_VAL": "قريب من الحد الأدنى لمنطقة القيمة (VAL)",
        "NEAR_POC": "قريب من نقطة التحكم (POC)",
        "ABOVE_VALUE_AREA": "فوق منطقة القيمة بالكامل",
        "BELOW_VALUE_AREA": "تحت منطقة القيمة بالكامل",
        "INSIDE_VALUE_AREA": "داخل منطقة القيمة (منطقة توازن)",
        "UNKNOWN": "غير محدد",
    }.get(location, location)
    parts.append(f"السعر حالياً {location_ar}")

    rel_vol = vp.get("relative_volume_pct") if vp else None
    if rel_vol is not None:
        if rel_vol >= HIGH_REL_VOLUME_THRESHOLD:
            parts.append(f"بحجم تداول أعلى بكثير من المعتاد ({rel_vol}%)")
        elif rel_vol >= MODERATE_REL_VOLUME_THRESHOLD:
            parts.append(f"بحجم تداول أعلى من المعتاد ({rel_vol}%)")

    if catalyst and catalyst.get("detected"):
        cal = catalyst.get("calendar", {})
        news = catalyst.get("news", {})
        if cal.get("detected"):
            ev = cal["events"][0]
            parts.append(f'وصدر للتو بيان "{ev["title"]}" ({ev["surprise"]}, قبل {ev["minutes_ago"]} دقيقة)')
        if news.get("detected"):
            h = news["headlines"][0]
            parts.append(f'وصدر خبر جديد قبل {h["minutes_ago"]} دقيقة: "{h["title"]}"')
    else:
        parts.append("بدون أي كاتاليست جديد بآخر دقائق")

    if vxn_factor:
        status = vxn_factor.get("status")
        current_vxn = vxn_factor.get("details", {}).get("current_vxn")
        if status == "red":
            parts.append(f"ومؤشر الخوف VXN مرتفع نسبياً ({current_vxn}) — توتر متصاعد بالسوق")
        elif status == "green":
            parts.append(f"ومؤشر الخوف VXN منخفض نسبياً ({current_vxn}) — هدوء بالسوق")

    return " — ".join(parts) + "."


def fuse(vp: dict, catalyst: dict, vxn_factor: dict = None) -> dict:
    """نقطة الدخول الرئيسية: يدمج Volume Profile + Catalyst Watcher + VXN بتنبيه واحد."""
    location = vp.get("price_location", "UNKNOWN") if vp else "UNKNOWN"
    rel_vol = vp.get("relative_volume_pct") if vp else None
    catalyst_detected = bool(catalyst and catalyst.get("detected"))
    at_structural_level = location in STRUCTURAL_LOCATIONS
    high_volume = rel_vol is not None and rel_vol >= HIGH_REL_VOLUME_THRESHOLD
    moderate_volume = rel_vol is not None and rel_vol >= MODERATE_REL_VOLUME_THRESHOLD
    elevated_fear = bool(vxn_factor and vxn_factor.get("status") == "red")

    if catalyst_detected and at_structural_level:
        alert_level = "HIGH_ATTENTION"
    elif catalyst_detected and high_volume:
        alert_level = "HIGH_ATTENTION"
    elif at_structural_level and high_volume:
        alert_level = "HIGH_ATTENTION"
    elif elevated_fear and (catalyst_detected or at_structural_level):
        alert_level = "HIGH_ATTENTION"
    elif catalyst_detected or at_structural_level or moderate_volume or elevated_fear:
        alert_level = "MODERATE_ATTENTION"
    else:
        alert_level = "LOW_ATTENTION"

    direction = _compute_direction(catalyst, vxn_factor)
    reason = _build_reason(vp, catalyst, vxn_factor, direction)

    return {
        "alert_level": alert_level,
        "directional_hint": direction,
        "reason": reason,
        "vxn_elevated_fear": elevated_fear,
        "is_advisory_only": True,  # تذكير دائم: لا يدخل بالقرار الرسمي
    }

"""
AUREX Pulse - Context Gate (بوابة 1 من استراتيجية السكالب الشخصية: "تحليل الأخبار الاقتصادية")

نستخدم confirmation_score الفعلي من AUREX AI (0-100) كميل مستمر، مو
القرار الرسمي المتشدد (LONG/SHORT بس). السبب: AUREX AI متحفّظ بقصد
(عتبات 70/30) لأنه يقرر صفقات كاملة — بوابة السكالب هون محتاجة بس
"وين الميل العام لليوم؟"، سؤال أخف بكثير.

"منطقة هدوء" حوالين نقطة الحياد (50 ± NEUTRAL_BAND): لو الـscore جوّا هاي
المنطقة، يعتبر "يوم هادئ" (بدون ميل إخباري/جيوسياسي حاسم) — وبهالحالة،
بوابة السياق تنسحب تلقائياً بـfusion.py، ونعتمد AMT + الكسر + VXN لحالهم
(بالضبط متل ما وصف المستخدم استراتيجيته: "لو كان اليوم هادئ، اتبع الشارت").

⚠️ قراءة فقط، باتجاه واحد (Pulse يقرأ من AUREX AI، أبداً العكس). لا كتابة
على signal_snapshot.json ولا أي تأثير على حسابه.

لو signal_snapshot.json غير متوفر أصلاً (أول تشغيل)، نتراجع لاتجاه
الكاتاليست (أخبار/تقويم) كبديل مؤقت.
"""

NEUTRAL_BAND = 10  # +/- 10 حوالين نقطة الحياد 50 = "يوم هادئ"


def get_daily_context(signal_snapshot: dict, catalyst_fallback_direction: str = "NEUTRAL") -> dict:
    """يرجع الانحياز اليومي (BULLISH/BEARISH/NEUTRAL) + مصدره."""
    if signal_snapshot and signal_snapshot.get("confirmation_score") is not None:
        score = signal_snapshot["confirmation_score"]
        final_decision = signal_snapshot.get("final_decision", {}) or {}

        if abs(score - 50) < NEUTRAL_BAND:
            direction = "NEUTRAL"   # يوم هادئ — نتبع AMT والكسر لحالهم
        elif score > 50:
            direction = "BULLISH"
        else:
            direction = "BEARISH"

        return {
            "direction": direction,
            "source": "aurex_ai_score",
            "raw_bias": final_decision.get("directional_bias"),
            "ai_status": final_decision.get("ai_status"),
            "confirmation_score": score,
        }

    # تراجع احتياطي: لا يوجد signal_snapshot.json متوفر بعد
    fallback_direction = catalyst_fallback_direction if catalyst_fallback_direction in ("BULLISH", "BEARISH") else "NEUTRAL"
    return {
        "direction": fallback_direction,
        "source": "catalyst_fallback",
        "raw_bias": None,
        "ai_status": None,
        "confirmation_score": None,
    }


def catalyst_only_direction(catalyst: dict) -> str:
    """يستخرج اتجاه تقريبي من الكاتاليست بس (أخبار/تقويم) — يُستخدم فقط
    كتراجع احتياطي لو signal_snapshot.json غير متوفر بعد."""
    if not catalyst or not catalyst.get("detected"):
        return "NEUTRAL"

    leans = []
    cal = catalyst.get("calendar", {})
    if cal.get("detected"):
        for ev in cal.get("events", []):
            if ev.get("surprise") == "BETTER_THAN_FORECAST":
                leans.append("BULLISH")
            elif ev.get("surprise") == "WORSE_THAN_FORECAST":
                leans.append("BEARISH")

    news = catalyst.get("news", {})
    if news.get("detected"):
        for h in news.get("headlines", []):
            if h.get("sentiment") == "Positive":
                leans.append("BULLISH")
            elif h.get("sentiment") == "Negative":
                leans.append("BEARISH")

    if not leans:
        return "NEUTRAL"
    bull, bear = leans.count("BULLISH"), leans.count("BEARISH")
    if bull > bear:
        return "BULLISH"
    if bear > bull:
        return "BEARISH"
    return "NEUTRAL"

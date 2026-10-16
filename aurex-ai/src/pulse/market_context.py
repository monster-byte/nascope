"""
AUREX Pulse - Market Context (طبقات وصفية فوق AMT وVXN للعرض بالداشبورد)
كل الدوال هون "تفسيرية" بس — تحوّل أرقام موجودة أصلاً (price_location،
POC سابق/حالي، VAH/VAL سابق/حالي، VXN الخام) لتصنيفات مفهومة بصرياً،
بدون أي حساب جديد من الصفر ولا مصدر بيانات إضافي.
"""

POC_MIGRATION_THRESHOLD_MULTIPLIER = 1.0  # بالصناديق (bin_size) — تغيّر أقل من هذا = مستقر
VALUE_AREA_CHANGE_THRESHOLD_PCT = 0.05    # 5%+ تغيّر بعرض منطقة القيمة = توسّع/انكماش حقيقي

VXN_TOO_LOW = 15.0   # تحت هذا = هدوء مفرط (خطر كسور كاذبة)
VXN_TOO_HIGH = 30.0  # فوق هذا = تقلب مفرط (خطر انعكاسات حادة Whipsaws)


def classify_amt_state(price_location: str) -> str:
    """يصنّف حالة السوق حسب نظرية المزاد (Auction Market Theory):
    ACCEPTANCE = السوق متوازن (داخل/عند POC)، TESTING_BOUNDARY = يختبر حافة
    منطقة القيمة، IMBALANCE_UP/DOWN = خارج منطقة القيمة كلياً (اتجاه واضح)."""
    if price_location in ("NEAR_POC", "INSIDE_VALUE_AREA"):
        return "ACCEPTANCE"
    if price_location in ("NEAR_VAH", "NEAR_VAL"):
        return "TESTING_BOUNDARY"
    if price_location == "ABOVE_VALUE_AREA":
        return "IMBALANCE_UP"
    if price_location == "BELOW_VALUE_AREA":
        return "IMBALANCE_DOWN"
    return "UNKNOWN"


def classify_poc_migration(old_poc: float, new_poc: float, bin_size: float) -> str:
    """يقارن POC الحالي بآخر تشغيل سابق — هل يتحرك لأعلى/أسفل/مستقر."""
    if old_poc is None or new_poc is None:
        return "UNKNOWN"
    threshold = bin_size * POC_MIGRATION_THRESHOLD_MULTIPLIER
    diff = new_poc - old_poc
    if abs(diff) < threshold:
        return "STABLE"
    return "UP" if diff > 0 else "DOWN"


def classify_value_area_width(old_vah: float, old_val: float, new_vah: float, new_val: float) -> str:
    """يقارن عرض منطقة القيمة (VAH-VAL) الحالي بآخر تشغيل — توسّع يعني
    دخول سيولة/تداول أوسع، انكماش يعني تركّز التداول بنطاق أضيق."""
    if None in (old_vah, old_val, new_vah, new_val):
        return "UNKNOWN"
    old_width = old_vah - old_val
    new_width = new_vah - new_val
    if old_width <= 0:
        return "UNKNOWN"
    change_pct = (new_width - old_width) / old_width
    if change_pct > VALUE_AREA_CHANGE_THRESHOLD_PCT:
        return "EXPANDING"
    if change_pct < -VALUE_AREA_CHANGE_THRESHOLD_PCT:
        return "CONTRACTING"
    return "STABLE"


def compute_volatility_check(vxn_factor: dict) -> dict:
    """يفحص هل VXN بمدى "صحي" للتداول — مو منخفض جداً (كسور كاذبة أكثر)
    ومو مرتفع جداً (انعكاسات حادة/Whipsaws أكثر)."""
    current_vxn = vxn_factor.get("details", {}).get("current_vxn") if vxn_factor else None
    if current_vxn is None:
        return {"available": False}

    not_too_low = current_vxn >= VXN_TOO_LOW
    not_too_high = current_vxn <= VXN_TOO_HIGH
    return {
        "available": True,
        "current_vxn": current_vxn,
        "not_too_low": not_too_low,
        "not_too_high": not_too_high,
        "trading_conditions_acceptable": not_too_low and not_too_high,
    }


# ============================================================
# طبقات إضافية لقسم 1 (Macro & News) وقسم 2 (USD Analysis) وقسم 4 (VXN)
# كلها وصفية/عرض فقط — ما بتدخل بقرار البوابات الأربعة.
# ============================================================

USD_NEUTRAL_BAND_PCT = 0.10   # تحت هذا التغيّر اليومي = الدولار محايد
USD_STRONG_BAND_PCT = 0.30    # فوق هذا = اتجاه واضح (مو "Slightly")


def fetch_series(symbol: str, period: str = "1d", interval: str = "5m", max_points: int = 120) -> list:
    """سلسلة إغلاقات قصيرة (للرسوم المصغّرة VXN / DXY). لو فشل الجلب: قائمة فاضية."""
    try:
        import yfinance as yf
        hist = yf.Ticker(symbol).history(period=period, interval=interval)
        if hist.empty:
            # بعض المؤشرات (مثل ^VXN) ما عندها بيانات 5 دقايق — نجرّب 15 دقيقة على 5 أيام
            hist = yf.Ticker(symbol).history(period="5d", interval="15m")
        if hist.empty:
            return []
        out = [{"time": idx.isoformat(), "value": round(float(v), 3)} for idx, v in hist["Close"].items() if v == v]
        return out[-max_points:]
    except Exception:
        return []


def classify_vxn_trend(series: list) -> str:
    """اتجاه VXN: مقارنة متوسط آخر 6 نقاط بالـ6 اللي قبلها."""
    vals = [p["value"] for p in series] if series else []
    if len(vals) < 12:
        return "UNKNOWN"
    recent = sum(vals[-6:]) / 6
    prior = sum(vals[-12:-6]) / 6
    if prior <= 0:
        return "UNKNOWN"
    chg = (recent - prior) / prior * 100
    if chg > 1.0:
        return "RISING"
    if chg < -1.0:
        return "FALLING"
    return "STABLE"


def classify_vxn_regime(vxn: float) -> str:
    if vxn is None:
        return "UNKNOWN"
    if vxn < VXN_TOO_LOW:
        return "LOW"
    if vxn > VXN_TOO_HIGH:
        return "HIGH"
    return "NORMAL"


def classify_usd_analysis(price_snapshot: dict, signal_snapshot: dict, dxy_series: list) -> dict:
    """تحليل الدولار (DXY) وأثره على ناسداك. عكسي: دولار أضعف = داعم لناسداك."""
    dxy = (price_snapshot or {}).get("DXY")
    if not dxy or dxy.get("last_price") is None:
        return {"available": False}

    chg = dxy.get("change_pct") or 0.0
    if abs(chg) < USD_NEUTRAL_BAND_PCT:
        trend = "NEUTRAL"
    elif chg > 0:
        trend = "BULLISH" if abs(chg) >= USD_STRONG_BAND_PCT else "SLIGHTLY_BULLISH"
    else:
        trend = "BEARISH" if abs(chg) >= USD_STRONG_BAND_PCT else "SLIGHTLY_BEARISH"

    momentum = "UNKNOWN"
    vals = [p["value"] for p in dxy_series] if dxy_series else []
    if len(vals) >= 12:
        d_recent = vals[-1] - vals[-6]
        d_prior = vals[-6] - vals[-12]
        if abs(d_recent) < 0.01:
            momentum = "FLAT"
        elif d_recent * d_prior > 0 and abs(d_recent) >= abs(d_prior):
            momentum = "STRENGTHENING"
        elif d_recent * d_prior > 0:
            momentum = "WEAKENING"
        else:
            momentum = "REVERSING"

    if trend in ("BEARISH", "SLIGHTLY_BEARISH"):
        nasdaq_impact = "SUPPORTIVE"
    elif trend in ("BULLISH", "SLIGHTLY_BULLISH"):
        nasdaq_impact = "PRESSURING"
    else:
        nasdaq_impact = "NEUTRAL"

    dxy_factor = ((signal_snapshot or {}).get("factors") or {}).get("dxy") or {}
    return {
        "available": True,
        "price": dxy.get("last_price"),
        "change": dxy.get("change"),
        "change_pct": chg,
        "trend": trend,
        "momentum": momentum,
        "nasdaq_impact": nasdaq_impact,
        "confidence": dxy_factor.get("score"),      # من AUREX AI (قراءة فقط)
        "series": dxy_series or [],
    }


def build_key_events(calendar_payload: dict, max_events: int = 4) -> list:
    """أحداث USD الأهم لليوم (توقيت نيويورك كما هو بملف التقويم)."""
    events = (calendar_payload or {}).get("events") or []
    usd = [e for e in events if e.get("country") == "USD" and e.get("impact") in ("High", "Medium")]
    if not usd:
        return []
    dates = [e["date"][:10] for e in usd if e.get("date")]
    if not dates:
        return []
    from datetime import datetime, timedelta, timezone
    try:
        ny_now = datetime.now(timezone.utc) - timedelta(hours=4)  # تقريب EDT، كافي لتحديد "اليوم"
        today = ny_now.strftime("%Y-%m-%d")
    except Exception:
        today = max(dates)
    todays = [e for e in usd if e["date"][:10] == today] or [e for e in usd if e["date"][:10] > today][:max_events]
    todays.sort(key=lambda e: (0 if e["impact"] == "High" else 1, e["date"]))
    out = [{
        "time": e["date"][11:16],
        "date": e["date"][:10],
        "title": e.get("title"),
        "impact": e.get("impact"),
        "forecast": e.get("forecast"),
        "previous": e.get("previous"),
        "actual": e.get("actual"),
    } for e in todays[:max_events]]
    out.sort(key=lambda x: (x["date"], x["time"]))
    return out


def build_news_analysis(usd: dict, daily_context: dict, key_events: list) -> dict:
    """ملخّص خبري بسيط (Rule-based، بدون LLM) من الأرقام الفعلية فقط."""
    direction = (daily_context or {}).get("direction", "UNKNOWN")
    parts = []
    if usd and usd.get("available"):
        word = {"BEARISH": "هابط", "SLIGHTLY_BEARISH": "هابط بشكل طفيف", "BULLISH": "صاعد",
                "SLIGHTLY_BULLISH": "صاعد بشكل طفيف", "NEUTRAL": "شبه ثابت"}.get(usd["trend"], "غير واضح")
        parts.append(f"الدولار (DXY) عند {usd['price']:.2f} بتغيّر {usd['change_pct']:+.2f}% — اتجاهه اليوم {word}.")
    high = [e for e in (key_events or []) if e.get("impact") == "High"]
    if high:
        parts.append(f"في {len(high)} حدث عالي التأثير اليوم ({high[0]['title']}) — توقّع تذبذب وقت صدوره.")
    elif key_events:
        parts.append("ما في أحداث عالية التأثير للدولار اليوم، فقط متوسطة.")
    else:
        parts.append("ما في أحداث مهمة للدولار اليوم.")
    parts.append({
        "BULLISH": "الميل الإخباري/الماكرو لليوم صاعد.",
        "BEARISH": "الميل الإخباري/الماكرو لليوم هابط.",
        "NEUTRAL": "يوم هادئ بدون ميل واضح — AMT هو اللي بيقرر.",
    }.get(direction, "الميل اليومي غير متوفر."))
    return {"text": " ".join(parts), "overall_bias": direction}

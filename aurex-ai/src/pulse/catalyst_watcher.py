"""
AUREX Pulse - Catalyst Watcher
يفحص هل صدر "كاتاليست أساسي طازج" (خبر مهم أو بيان اقتصادي عالي الأهمية)
بآخر دقايق قليلة — يعيد استخدام نفس NewsAPI والتقويم الاقتصادي الموجودين
أصلاً بالمحرك الأساسي (AUREX AI)، بدون أي مصدر بيانات أو اشتراك إضافي.

الفكرة: متداول فريم 5 دقايق محتاج يعرف "هل في شي جديد صار هلق بالضبط؟"
مو ملخص عام لآخر 24 ساعة (هذا شغل news_factor.py الحالي بالمحرك الأساسي).
"""

import os
from datetime import datetime, timedelta, timezone

from vaderSentiment.vaderSentiment import SentimentIntensityAnalyzer

from ..signal.config import NEWS_QUERY
from ..signal.macro_factor import _classify_event_direction, _parse_number
from ..signal.news_factor import fetch_headlines

FRESH_WINDOW_MINUTES = 6    # مضبوط للسكالب (كان 15) — أي شي أقدم من هذا يعتبر "مو طازج"
NEWS_FRESH_QUERY = NEWS_QUERY
_analyzer = SentimentIntensityAnalyzer()


def _minutes_ago(dt: datetime) -> float:
    now = datetime.now(timezone.utc)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return round((now - dt).total_seconds() / 60, 1)


def _parse_iso(ts: str):
    try:
        return datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except Exception:
        return None


def check_fresh_news(window_minutes: int = FRESH_WINDOW_MINUTES) -> dict:
    """يفحص هل في خبر جديد نُشر بآخر X دقيقة، عبر نفس NewsAPI المستخدم بالعامل الأساسي."""
    api_key = os.environ.get("NEWSAPI_KEY")
    if not api_key:
        return {"detected": False, "reason": "NEWSAPI_KEY not set"}

    try:
        headlines = fetch_headlines(api_key, query=NEWS_FRESH_QUERY, max_articles=15)
    except Exception as e:
        return {"detected": False, "reason": f"news_fetch_failed: {e}"}

    fresh = []
    for h in headlines:
        dt = _parse_iso(h.get("publishedAt") or "")
        if dt is None:
            continue
        age = _minutes_ago(dt)
        if 0 <= age <= window_minutes:
            compound = _analyzer.polarity_scores(h["title"] or "")["compound"]
            label = "Positive" if compound > 0.2 else ("Negative" if compound < -0.2 else "Neutral")
            fresh.append({**h, "minutes_ago": age, "sentiment": label})

    if not fresh:
        return {"detected": False, "reason": "no_fresh_headlines_in_window", "window_minutes": window_minutes}

    fresh.sort(key=lambda x: x["minutes_ago"])
    return {"detected": True, "type": "news", "headlines": fresh[:3], "window_minutes": window_minutes}


def check_fresh_calendar_event(calendar_payload: dict, window_minutes: int = FRESH_WINDOW_MINUTES) -> dict:
    """يفحص هل صدر بيان اقتصادي عالي الأهمية بآخر X دقيقة، وهل كان أعلى/أقل من التوقعات
    (نفس منطق التصنيف المستخدم بـ macro_factor.py، بدون تكرار الكود)."""
    events = calendar_payload.get("high_impact_events", []) if calendar_payload else []
    fresh = []

    for ev in events:
        actual = _parse_number(ev.get("actual"))
        forecast = _parse_number(ev.get("forecast"))
        raw_date = ev.get("date")
        if actual is None or forecast is None or not raw_date:
            continue  # لسا ما صدر البيان، أو ما فيه تاريخ واضح

        dt = _parse_iso(raw_date)
        if dt is None:
            continue

        age = _minutes_ago(dt)
        if not (0 <= age <= window_minutes):
            continue

        direction = _classify_event_direction(ev.get("title", ""))
        if direction is None:
            surprise = "UNKNOWN"
        elif direction == "lower_is_good":
            surprise = "BETTER_THAN_FORECAST" if actual < forecast else (
                "WORSE_THAN_FORECAST" if actual > forecast else "IN_LINE")
        else:
            surprise = "BETTER_THAN_FORECAST" if actual > forecast else (
                "WORSE_THAN_FORECAST" if actual < forecast else "IN_LINE")

        fresh.append({
            "title": ev.get("title"),
            "actual": actual,
            "forecast": forecast,
            "surprise": surprise,
            "minutes_ago": age,
        })

    if not fresh:
        return {"detected": False, "reason": "no_fresh_calendar_events_in_window", "window_minutes": window_minutes}

    fresh.sort(key=lambda x: x["minutes_ago"])
    return {"detected": True, "type": "calendar", "events": fresh, "window_minutes": window_minutes}


def compute_catalyst(calendar_payload: dict, window_minutes: int = FRESH_WINDOW_MINUTES) -> dict:
    """نقطة الدخول الرئيسية: يدمج فحص الأخبار والتقويم الاقتصادي، ويرجع
    أقوى/أحدث كاتاليست موجود حالياً (إن وجد)."""
    news_result = check_fresh_news(window_minutes)
    calendar_result = check_fresh_calendar_event(calendar_payload, window_minutes)

    detected = news_result.get("detected") or calendar_result.get("detected")

    return {
        "detected": detected,
        "window_minutes": window_minutes,
        "news": news_result,
        "calendar": calendar_result,
    }

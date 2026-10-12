"""
AUREX Pulse - Scalp Track Record
يسجّل ويقيّم إشارات السكالب الفعلية (SCALP_BULLISH/SCALP_BEARISH من الأربع
بوابات) — منفصل كلياً عن track_record الخاص بـ AUREX AI (اللي يقيس بوابة
السياق بس، على أفق 24 ساعة، مو إشارات السكالب نفسها).

الفرق الجوهري عن track_record الأساسي:
- يسجّل بس لما final_signal يكون SCALP_BULLISH أو SCALP_BEARISH فعلياً
  (مو أي قرار AUREX AI)، ويتجنّب تسجيل نفس الإشارة مرة ثانية وهي مستمرة.
- أفق تقييم قصير (15 دقيقة افتراضياً) يناسب السكالب، مو 24 ساعة.
- يحسب price_change_pct كمقياس أداء مبدئي (مو Avg R/Profit Factor بعد —
  هذول يحتاجوا منطق Entry/Stop/Target خاص بالسكالب غير مبني لسا).

الملفات:
- data/pulse/scalp_track_log.json      (كل الإشارات المسجّلة + حالة التقييم)
- data/pulse/scalp_track_summary.json  (ملخّص: win rate, عدد، آخر الإشارات)
"""

import json
import os
from datetime import datetime, timedelta, timezone

LOG_PATH = "data/pulse/scalp_track_log.json"
SUMMARY_PATH = "data/pulse/scalp_track_summary.json"

VERIFICATION_MINUTES = 15   # أفق تقييم يناسب السكالب (مو 24 ساعة زي AUREX AI)
NOISE_THRESHOLD_PCT = 0.02  # حركة أقل من هذا % تعتبر "بدون حركة حقيقية" (تذبذب عادي)


def _load_log() -> list:
    if not os.path.exists(LOG_PATH):
        return []
    with open(LOG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def _save_log(entries: list):
    os.makedirs(os.path.dirname(LOG_PATH), exist_ok=True)
    with open(LOG_PATH, "w", encoding="utf-8") as f:
        json.dump(entries, f, ensure_ascii=False, indent=2)


def log_signal(fusion_result: dict, current_price: float) -> dict:
    """يسجّل إشارة سكالب جديدة بس لو final_signal فعلي (BULLISH/BEARISH)
    ومختلف عن آخر إشارة مسجّلة (يتجنّب التكرار وقت استمرار نفس الإعداد)."""
    final_signal = fusion_result.get("final_signal") if fusion_result else None
    if final_signal not in ("SCALP_BULLISH", "SCALP_BEARISH"):
        return {"logged": False, "reason": "no_scalp_signal"}

    entries = _load_log()

    if entries:
        last = entries[-1]
        # نفس الإشارة لسا مستمرة ولسا ما انتهى وقت تقييمها؟ ما نكررها
        if last.get("final_signal") == final_signal and not last.get("verified"):
            return {"logged": False, "reason": "duplicate_ongoing_signal"}

    entry = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "final_signal": final_signal,
        "direction": "LONG" if final_signal == "SCALP_BULLISH" else "SHORT",
        "entry_price": round(float(current_price), 2),
        "verified": False,
        "outcome": None,
        "price_after": None,
        "price_change_pct": None,
        "verified_at": None,
    }
    entries.append(entry)
    _save_log(entries)
    return {"logged": True, "entry": entry}


def _find_price_at_or_after(candles: list, target_dt) -> float:
    """يرجع سعر إغلاق أقرب شمعة بعد (أو بالظبط عند) الوقت المطلوب."""
    for c in candles:
        try:
            c_dt = datetime.fromisoformat(c["time"])
        except Exception:
            continue
        if c_dt >= target_dt:
            return float(c["close"])
    return None


def verify_pending(price_snapshot: dict, symbol_key: str = "NASDAQ_FUTURES") -> dict:
    """يفحص كل الإشارات غير المقيّمة اللي مرّ عليها وقت التقييم (15 دقيقة)،
    ويحدد هل تحرك السعر بنفس الاتجاه المتوقع فعلاً."""
    entries = _load_log()
    if not entries:
        return {"checked": 0, "newly_verified": 0}

    candles = price_snapshot.get(symbol_key, {}).get("candles", []) if price_snapshot else []
    if not candles:
        return {"checked": 0, "newly_verified": 0, "reason": "no_candles"}

    now = datetime.now(timezone.utc)
    newly_verified = 0

    for entry in entries:
        if entry.get("verified"):
            continue

        entry_time = datetime.fromisoformat(entry["timestamp"])
        target_time = entry_time + timedelta(minutes=VERIFICATION_MINUTES)
        if now < target_time:
            continue  # لسا ما اكتمل وقت التقييم

        price_after = _find_price_at_or_after(candles, target_time)
        if price_after is None:
            continue  # ما لقينا شمعة كافية بعد (نادر، نحاول بالتشغيل الجاي)

        entry_price = entry["entry_price"]
        change_pct = round(((price_after - entry_price) / entry_price) * 100, 4)

        if abs(change_pct) < NOISE_THRESHOLD_PCT:
            outcome = "flat"  # حركة ضمن حدود التذبذب العادي، لا نحسبها ربح ولا خسارة
        elif entry["direction"] == "LONG":
            outcome = "correct" if change_pct > 0 else "incorrect"
        else:  # SHORT
            outcome = "correct" if change_pct < 0 else "incorrect"

        entry["verified"] = True
        entry["outcome"] = outcome
        entry["price_after"] = round(price_after, 2)
        entry["price_change_pct"] = change_pct
        entry["verified_at"] = now.isoformat()
        newly_verified += 1

    _save_log(entries)
    return {"checked": len(entries), "newly_verified": newly_verified}


def build_summary() -> dict:
    """يبني ملخّص الأداء (win rate + آخر الإشارات) ويحفظه بملف منفصل للداشبورد."""
    entries = _load_log()
    graded = [e for e in entries if e.get("verified") and e.get("outcome") in ("correct", "incorrect")]
    correct = [e for e in graded if e["outcome"] == "correct"]
    flat = [e for e in entries if e.get("verified") and e.get("outcome") == "flat"]

    win_rate = round((len(correct) / len(graded)) * 100, 1) if graded else None

    avg_win_pct = None
    avg_loss_pct = None
    wins = [abs(e["price_change_pct"]) for e in correct]
    losses = [abs(e["price_change_pct"]) for e in graded if e["outcome"] == "incorrect"]
    if wins:
        avg_win_pct = round(sum(wins) / len(wins), 4)
    if losses:
        avg_loss_pct = round(sum(losses) / len(losses), 4)

    summary = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "verification_window_minutes": VERIFICATION_MINUTES,
        "total_signals_logged": len(entries),
        "graded_signals": len(graded),
        "flat_signals": len(flat),
        "pending_signals": len(entries) - len(graded) - len(flat),
        "win_rate_pct": win_rate,
        "avg_win_pct": avg_win_pct,
        "avg_loss_pct": avg_loss_pct,
        "note": (
            "مقياس أولي (price_change_pct) — Avg R وProfit Factor الحقيقيين "
            "يحتاجوا منطق Entry/Stop/Target خاص بالسكالب (غير مبني بعد)."
        ),
        "recent_entries": list(reversed(entries))[:15],
    }

    os.makedirs(os.path.dirname(SUMMARY_PATH), exist_ok=True)
    with open(SUMMARY_PATH, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=2)

    return summary

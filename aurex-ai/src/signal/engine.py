"""
AUREX AI - Signal Engine (المرحلة 2)
يجمع كل العوامل، يحسب Confirmation Score و Trade Probability والقرار النهائي (Final Decision)
مطابق لهيكلية لوحة "AI Signal & Confirmation" بالداشبورد الأصلي
"""

import json
import os
from datetime import datetime, timezone

from .config import WEIGHTS, DECISION_THRESHOLDS, OUTPUT_PATH
from .price_factors import (
    compute_mega_cap_alignment,
    compute_market_regime,
    compute_vxn_factor,
    compute_us10y_factor,
    compute_dxy_factor,
)
from .macro_factor import compute_macro_factor
from .news_factor import compute_news_factor
from .patent_factor import compute_patent_factor


def load_json(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def compute_all_factors(price_snapshot: dict, calendar_payload: dict) -> dict:
    factors = {
        "mega_cap_alignment": compute_mega_cap_alignment(price_snapshot),
        "market_regime": compute_market_regime(),
        "vxn": compute_vxn_factor(price_snapshot),
        "us10y": compute_us10y_factor(),
        "dxy": compute_dxy_factor(),
        "macro": compute_macro_factor(calendar_payload),
        "news_sentiment": compute_news_factor(),
        "patent_momentum": compute_patent_factor(),
    }
    return factors


def compute_confirmation_score(factors: dict) -> float:
    total = 0.0
    for name, weight in WEIGHTS.items():
        total += factors[name]["score"] * weight
    return round(total, 2)


def estimate_trade_probability(confirmation_score: float) -> float:
    """
    تقدير مبدئي (heuristic) لاحتمالية نجاح الصفقة بالاعتماد على Confirmation Score.
    ⚠️ هاي معايرة أولية بس — رح تُضبط بدقة أكبر لاحقاً بمرحلة الـ Backtest
    (بمقارنة توقعات المحرك بنتائج فعلية تاريخية).
    """
    probability = 50 + (confirmation_score - 50) * 0.6
    return round(max(5.0, min(95.0, probability)), 2)


def determine_market_regime_label(factors: dict) -> str:
    regime_details = factors["market_regime"]["details"]
    return regime_details.get("regime", "NEUTRAL")


def determine_final_decision(confirmation_score: float, regime_label: str) -> dict:
    """
    عتبات متناظرة حول نقطة الحياد (50): البيع يحتاج نفس درجة القناعة اللي يحتاجها
    الشراء بالضبط (مرآة العتبة)، مو بس "أي شي تحت 50". هذا يمنع تنفيذ صفقات بيع
    بثقة ضعيفة بينما الشراء يحتاج ثقة عالية.

    مثال بالعتبات الافتراضية (approve_min_score=70):
    - score >= 70 وسياق صاعد        → APPROVED LONG
    - score <= 30 وسياق هابط        → APPROVED SHORT (30 = مرآة الـ70 حول نقطة الحياد 50)
    - 30 < score < 70                → HOLD / MONITOR (منطقة عدم يقين، بلا اتجاه واضح بالاتجاهين)
    - أي تعارض (score متطرف لكن اتجاه السعر يخالفه) → REJECT / AVOID احترازياً
    """
    thresholds = DECISION_THRESHOLDS
    is_bearish = "BEARISH" in regime_label

    approve_min_long = thresholds["approve_min_score"]      # مثلاً 70
    approve_max_short = 100 - approve_min_long               # المرآة حول 50 → 30

    if confirmation_score >= approve_min_long and not is_bearish:
        status, bias = "APPROVED", "LONG"
    elif confirmation_score <= approve_max_short and is_bearish:
        status, bias = "APPROVED", "SHORT"
    elif approve_max_short < confirmation_score < approve_min_long:
        status, bias = "HOLD / MONITOR", "NEUTRAL"
    else:
        # حالات تعارض: score متطرف بس اتجاه السعر يخالفه → نتجنب التنفيذ احترازياً
        status, bias = "REJECT", "AVOID"

    return {"ai_status": status, "directional_bias": bias}


def run():
    print("=== AUREX AI | Signal Engine Run ===")

    price_snapshot = load_json("data/prices/snapshot_1D.json")
    calendar_payload = load_json("data/calendar/calendar_thisweek.json")

    if not price_snapshot:
        print("[WARN] لا يوجد data/prices/snapshot_1D.json — شغّل طبقة البيانات أولاً")

    print("[1/3] حساب العوامل...")
    factors = compute_all_factors(price_snapshot, calendar_payload)

    print("[2/3] حساب Confirmation Score و Trade Probability...")
    confirmation_score = compute_confirmation_score(factors)
    trade_probability = estimate_trade_probability(confirmation_score)
    regime_label = determine_market_regime_label(factors)
    decision = determine_final_decision(confirmation_score, regime_label)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "weights": WEIGHTS,
        "factors": factors,
        "confirmation_score": confirmation_score,
        "trade_probability": trade_probability,
        "market_regime": regime_label,
        "final_decision": decision,
    }

    print("[3/3] حفظ النتيجة...")
    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
                json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nConfirmation Score : {confirmation_score}%")  
    print(f"Trade Probability  : {trade_probability}%")
    print(f"Market Regime      : {regime_label}")
    print(f"Final Decision     : {decision['ai_status']} ({decision['directional_bias']})")
    print(f"\n[OK] تم حفظ {OUTPUT_PATH}")
    print("=== انتهى ✅ ===")


if __name__ == "__main__":
    run()

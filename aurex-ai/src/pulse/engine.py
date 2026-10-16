"""
AUREX Pulse - Intraday Engine (محرك السكالب الفعلي)
خط أنابيب متسلسل (4 بوابات) مطابق لاستراتيجية السكالب الشخصية:
السياق اليومي → AMT (Volume Profile) → تأكيد الكسر (جلسة نيويورك) → VXN.
بالإضافة لطبقات وصفية (حالة AMT، هجرة POC، اتساع منطقة القيمة، فحص
التقلب) ونقاط دخول/وقف/هدف فعلية لإشارات السكالب المؤكدة.

يحفظ النتيجة بـ data/intraday/intraday_snapshot.json — ملف منفصل كلياً.

⚠️ هذا المحرك استشاري بحت (Pulse — Intraday Assistant):
- **يقرأ فقط** (قراءة باتجاه واحد) من signal_snapshot.json.
- **لا يكتب أبداً** على signal_snapshot.json ولا يدخل بأي شكل بحساب
  confirmation_score أو القرار الرسمي لمحرك AUREX AI.
"""

import json
import os
from datetime import datetime, timezone

from .volume_profile import compute_volume_profile
from .catalyst_watcher import compute_catalyst
from .breakout_confirm import detect_breakout
from .context_gate import get_daily_context, catalyst_only_direction
from .fusion import fuse
from .scalp_track_record import log_signal, verify_pending, build_summary
from .scalp_position import compute_scalp_position
from .market_context import (
    classify_amt_state,
    classify_poc_migration,
    classify_value_area_width,
    compute_volatility_check,
    fetch_series,
    classify_vxn_trend,
    classify_vxn_regime,
    classify_usd_analysis,
    build_key_events,
    build_news_analysis,
)
from ..signal.price_factors import compute_vxn_factor
from ..data.price_fetcher import fetch_ohlcv
from ..data.config import NASDAQ_FUTURES

OUTPUT_PATH = "data/intraday/intraday_snapshot.json"


def load_json(path: str):
    if not os.path.exists(path):
        return {}
    with open(path, "r", encoding="utf-8") as f:
        return json.load(f)


def run():
    print("=== AUREX Pulse | Intraday Engine Run ===")

    price_snapshot = load_json("data/prices/snapshot_1D.json")
    calendar_payload = load_json("data/calendar/calendar_thisweek.json")
    signal_snapshot = load_json("data/signal/signal_snapshot.json")  # قراءة فقط
    previous_snapshot = load_json(OUTPUT_PATH)  # نقرأه قبل ما نستبدله — لتتبّع هجرة POC

    if not price_snapshot:
        print("[WARN] لا يوجد data/prices/snapshot_1D.json — شغّل طبقة البيانات أولاً")
    if not signal_snapshot:
        print("[WARN] لا يوجد data/signal/signal_snapshot.json بعد — بوابة السياق رح تتراجع لاتجاه الكاتاليست بس")

    print("[1/9] جلب شموع دقيقة واحدة طازجة (لـMicro Profile الخاص بالسكالب)...")
    micro_candles = None
    try:
        one_min_data = fetch_ohlcv(NASDAQ_FUTURES, timeframe="1m")
        if one_min_data and one_min_data.get("candles"):
            micro_candles = one_min_data["candles"]
            os.makedirs("data/prices", exist_ok=True)
            with open("data/prices/snapshot_1m.json", "w", encoding="utf-8") as f:
                json.dump(one_min_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] فشل جلب بيانات 1 دقيقة (رح نتراجع تلقائياً لشموع 5 دقايق): {e}")
        micro_candles = None

    print("[2/9] بوابة 2: حساب Developing Volume Profile + Micro Profile (AMT)...")
    vp = compute_volume_profile(price_snapshot, micro_candles=micro_candles)

    print("[3/9] طبقات وصفية AMT إضافية (حالة السوق، هجرة POC، اتساع منطقة القيمة)...")
    try:
        prev_vp = previous_snapshot.get("volume_profile", {}) if previous_snapshot else {}
        amt_state = classify_amt_state(vp.get("price_location"))
        poc_migration = classify_poc_migration(prev_vp.get("poc"), vp.get("poc"), vp.get("bin_size_points", 6))
        value_area_trend = classify_value_area_width(prev_vp.get("vah"), prev_vp.get("val"), vp.get("vah"), vp.get("val"))
        market_structure = {
            "amt_state": amt_state,
            "poc_migration": poc_migration,
            "value_area_trend": value_area_trend,
        }
    except Exception as e:
        print(f"[WARN] فشل حساب الطبقات الوصفية: {e}")
        market_structure = {"amt_state": "UNKNOWN", "poc_migration": "UNKNOWN", "value_area_trend": "UNKNOWN"}

    print("[4/9] حساب مؤشر الخوف VXN اللحظي (مدخل لبوابة 4) + فحص التقلب...")
    try:
        vxn_factor = compute_vxn_factor(price_snapshot)
    except Exception as e:
        print(f"[WARN] فشل حساب VXN لمحرك Pulse: {e}")
        vxn_factor = {"factor": "vxn", "score": 50.0, "status": "yellow", "details": {"error": str(e)}}
    volatility_check = compute_volatility_check(vxn_factor)
    vxn_series = fetch_series("^VXN")
    vxn_view = {
        "regime": classify_vxn_regime(vxn_factor.get("details", {}).get("current_vxn")),
        "trend": classify_vxn_trend(vxn_series),
        "series": vxn_series,
    }

    print("[5/9] فحص الكاتاليست الطازج (مدخل احتياطي لبوابة 1 لو AUREX AI غير متوفر)...")
    catalyst = compute_catalyst(calendar_payload)

    print("[6/9] بوابة 1: قراءة الانحياز اليومي من AUREX AI (قراءة فقط)...")
    daily_context = get_daily_context(signal_snapshot, catalyst_only_direction(catalyst))
    try:
        usd_analysis = classify_usd_analysis(price_snapshot, signal_snapshot, fetch_series("DX-Y.NYB"))
        key_events = build_key_events(calendar_payload)
        news_analysis = build_news_analysis(usd_analysis, daily_context, key_events)
    except Exception as e:
        print(f"[WARN] فشل حساب USD/الأحداث: {e}")
        usd_analysis, key_events, news_analysis = {"available": False}, [], {"text": "", "overall_bias": "UNKNOWN"}

    print("[7/9] بوابة 3: فحص تأكيد الكسر (جلسة نيويورك فقط)...")
    try:
        all_candles = price_snapshot.get("NASDAQ_FUTURES", {}).get("candles", [])
        breakout = detect_breakout(all_candles, vp.get("val"), vp.get("vah"))
    except Exception as e:
        print(f"[WARN] فشل فحص تأكيد الكسر: {e}")
        breakout = {"status": "error", "in_ny_session": False, "error": str(e)}

    print("[8/9] دمج البوابات الأربعة + حساب نقاط الدخول/الوقف/الهدف...")
    fusion_result = fuse(vp, daily_context, breakout, vxn_factor)
    scalp_position = compute_scalp_position(fusion_result, vp)

    print("[9/9] تسجيل وتقييم إشارات السكالب الفعلية (Scalp Track Record)...")
    try:
        log_result = log_signal(fusion_result, vp.get("current_price"), scalp_position)
        verify_result = verify_pending(price_snapshot)
        scalp_summary = build_summary()
    except Exception as e:
        print(f"[WARN] فشل تسجيل/تقييم Scalp Track Record: {e}")
        log_result = {"logged": False, "reason": f"error: {e}"}
        verify_result = {"checked": 0, "newly_verified": 0}
        scalp_summary = {}

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "AUREX Pulse (advisory only — لا يدخل بالقرار الرسمي)",
        "volume_profile": vp,
        "market_structure": market_structure,
        "vxn": vxn_factor,
        "volatility_check": volatility_check,
        "vxn_view": vxn_view,
        "usd_analysis": usd_analysis,
        "key_events": key_events,
        "news_analysis": news_analysis,
        "catalyst": catalyst,
        "daily_context": daily_context,
        "breakout": breakout,
        "fusion": fusion_result,
        "scalp_position": scalp_position,
        "scalp_track_record": scalp_summary,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nPrice Location     : {vp.get('price_location')}")
    print(f"POC / VAL / VAH    : {vp.get('poc')} / {vp.get('val')} / {vp.get('vah')}")
    print(f"AMT State          : {market_structure.get('amt_state')} | POC Migration: {market_structure.get('poc_migration')} | VA: {market_structure.get('value_area_trend')}")
    mp = vp.get("micro_profile", {})
    if mp.get("available"):
        print(f"Micro Profile      : source={mp.get('source_timeframe')} | POC={mp.get('poc')} | location={mp.get('price_location')}")
    else:
        print(f"Micro Profile      : غير متوفر ({mp.get('reason')})")
    print(f"Gate 1 (Context)   : direction={daily_context.get('direction')} (source={daily_context.get('source')})")
    print(f"Gate 3 (Breakout)  : {breakout.get('status')} (in_ny_session={breakout.get('in_ny_session')})")
    print(f"Gate 4 (VXN)       : {vxn_factor.get('status')} ({vxn_factor.get('details', {}).get('current_vxn')}) | Conditions OK: {volatility_check.get('trading_conditions_acceptable')}")
    print(f"Final Signal       : {fusion_result.get('final_signal')}")
    if scalp_position.get("available"):
        print(f"Scalp Position     : {scalp_position['direction']} Entry={scalp_position['entry']} SL={scalp_position['stop_loss']} TP1={scalp_position['take_profit_1']} TP2={scalp_position['take_profit_2']}")
    else:
        print(f"Scalp Position     : غير متوفر ({scalp_position.get('reason')})")
    print(f"Scalp Log          : logged={log_result.get('logged')} ({log_result.get('reason', 'ok')})")
    print(f"Scalp Win Rate     : {scalp_summary.get('win_rate_pct')}% ({scalp_summary.get('graded_signals')} مُقيّمة)")
    print(f"\n[OK] تم حفظ {OUTPUT_PATH}")
    print("=== انتهى ✅ ===")


if __name__ == "__main__":
    run()

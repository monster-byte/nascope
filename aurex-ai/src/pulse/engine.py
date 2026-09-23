"""
AUREX Pulse - Intraday Engine (المحرك الثاني، منفصل تماماً عن AUREX AI الأساسي)
يربط Developing Volume Profile + Catalyst Watcher + Fusion مع بعض، ويحفظ
data/intraday/intraday_snapshot.json — ملف منفصل كلياً عن signal_snapshot.json.

⚠️ هذا المحرك استشاري بحت (Pulse — Intraday Assistant). لا يكتب ولا يقرأ من
signal_snapshot.json، ولا يدخل بأي شكل بحساب confirmation_score أو القرار
الرسمي لمحرك AUREX AI. الهدف مساعدة متداول فريم 5 دقايق يشوف سياق إضافي
بعينه، القرار يضل له.
"""

import json
import os
from datetime import datetime, timezone

from .volume_profile import compute_volume_profile
from .catalyst_watcher import compute_catalyst
from .fusion import fuse
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

    if not price_snapshot:
        print("[WARN] لا يوجد data/prices/snapshot_1D.json — شغّل طبقة البيانات أولاً")

    print("[1/5] جلب شموع دقيقة واحدة طازجة (لـMicro Profile الخاص بالسكالب)...")
    micro_candles = None
    try:
        one_min_data = fetch_ohlcv(NASDAQ_FUTURES, timeframe="1m")
        if one_min_data and one_min_data.get("candles"):
            micro_candles = one_min_data["candles"]
            # نحفظها بملف منفصل تماماً — شفافية/تصحيح أخطاء بس، ما يقرأه أي محرك تاني
            os.makedirs("data/prices", exist_ok=True)
            with open("data/prices/snapshot_1m.json", "w", encoding="utf-8") as f:
                json.dump(one_min_data, f, ensure_ascii=False, indent=2)
    except Exception as e:
        print(f"[WARN] فشل جلب بيانات 1 دقيقة (رح نتراجع تلقائياً لشموع 5 دقايق): {e}")
        micro_candles = None

    print("[2/5] حساب Developing Volume Profile + Micro Profile...")
    vp = compute_volume_profile(price_snapshot, micro_candles=micro_candles)

    print("[3/5] حساب مؤشر الخوف VXN اللحظي...")
    try:
        vxn_factor = compute_vxn_factor(price_snapshot)
    except Exception as e:
        print(f"[WARN] فشل حساب VXN لمحرك Pulse: {e}")
        vxn_factor = {"factor": "vxn", "score": 50.0, "status": "yellow", "details": {"error": str(e)}}

    print("[4/5] فحص الكاتاليست الطازج (أخبار + تقويم اقتصادي)...")
    catalyst = compute_catalyst(calendar_payload)

    print("[5/5] دمج النتائج الثلاث بتنبيه استشاري واحد...")
    fusion_result = fuse(vp, catalyst, vxn_factor)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "AUREX Pulse (advisory only — لا يدخل بالقرار الرسمي)",
        "volume_profile": vp,
        "vxn": vxn_factor,
        "catalyst": catalyst,
        "fusion": fusion_result,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nPrice Location     : {vp.get('price_location')}")
    print(f"POC / VAL / VAH    : {vp.get('poc')} / {vp.get('val')} / {vp.get('vah')}")
    print(f"Relative Volume    : {vp.get('relative_volume_pct')}%")
    mp = vp.get("micro_profile", {})
    if mp.get("available"):
        print(f"Micro Profile      : source={mp.get('source_timeframe')} | POC={mp.get('poc')} | location={mp.get('price_location')}")
    else:
        print(f"Micro Profile      : غير متوفر ({mp.get('reason')})")
    print(f"VXN Status         : {vxn_factor.get('status')} ({vxn_factor.get('details', {}).get('current_vxn')})")
    print(f"Catalyst Detected  : {catalyst.get('detected')}")
    print(f"Alert Level        : {fusion_result.get('alert_level')} ({fusion_result.get('directional_hint')})")
    print(f"\n[OK] تم حفظ {OUTPUT_PATH}")
    print("=== انتهى ✅ ===")


if __name__ == "__main__":
    run()

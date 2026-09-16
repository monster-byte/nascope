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

    print("[1/3] حساب Developing Volume Profile...")
    vp = compute_volume_profile(price_snapshot)

    print("[2/3] فحص الكاتاليست الطازج (أخبار + تقويم اقتصادي)...")
    catalyst = compute_catalyst(calendar_payload)

    print("[3/3] دمج النتيجتين بتنبيه استشاري واحد...")
    fusion_result = fuse(vp, catalyst)

    result = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "engine": "AUREX Pulse (advisory only — لا يدخل بالقرار الرسمي)",
        "volume_profile": vp,
        "catalyst": catalyst,
        "fusion": fusion_result,
    }

    os.makedirs(os.path.dirname(OUTPUT_PATH), exist_ok=True)
    with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    print(f"\nPrice Location     : {vp.get('price_location')}")
    print(f"POC / VAL / VAH    : {vp.get('poc')} / {vp.get('val')} / {vp.get('vah')}")
    print(f"Relative Volume    : {vp.get('relative_volume_pct')}%")
    print(f"Catalyst Detected  : {catalyst.get('detected')}")
    print(f"Alert Level        : {fusion_result.get('alert_level')} ({fusion_result.get('directional_hint')})")
    print(f"\n[OK] تم حفظ {OUTPUT_PATH}")
    print("=== انتهى ✅ ===")


if __name__ == "__main__":
    run()

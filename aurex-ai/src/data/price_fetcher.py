"""
AUREX AI - Price Fetcher
يسحب بيانات OHLCV لكل الرموز المعرّفة في config.py عبر yfinance
ويحفظها كملفات JSON منظمة تحت مجلد data/prices/
"""

import json
import os
from datetime import datetime, timezone

import yfinance as yf

from .config import ALL_SYMBOLS, OUTPUT_DIR, TIMEFRAME_MAP


def fetch_ohlcv(symbol: str, timeframe: str = "1D"):
    """يجلب الشموع لرمز واحد على فريم زمني محدد."""
    if timeframe not in TIMEFRAME_MAP:
        raise ValueError(f"Unsupported timeframe: {timeframe}")

    params = TIMEFRAME_MAP[timeframe]
    ticker = yf.Ticker(symbol)
    hist = ticker.history(period=params["period"], interval=params["interval"])

    if hist.empty:
        return None

    candles = [
        {
            "time": idx.isoformat(),
            "open": round(float(row["Open"]), 4),
            "high": round(float(row["High"]), 4),
            "low": round(float(row["Low"]), 4),
            "close": round(float(row["Close"]), 4),
            "volume": int(row["Volume"]) if not pd_isna(row["Volume"]) else 0,
        }
        for idx, row in hist.iterrows()
    ]

    last = hist.iloc[-1]

    # نجيب إغلاق الجلسة السابقة الرسمي من yfinance مباشرة (مو الشمعة قبل الأخيرة بـ5 دقايق فقط)
    # لأن بيانات "1D" فعلياً شموع كل 5 دقايق، وإغلاق الشمعة السابقة مباشرة لا يمثّل "تغيّر اليوم"
    prev_close = None
    try:
        fast = ticker.fast_info
        prev_close = fast.get("previousClose") or fast.get("previous_close")
    except Exception:
        prev_close = None

    if not prev_close:
        try:
            prev_close = ticker.info.get("previousClose")
        except Exception:
            prev_close = None

    if not prev_close:
        # حل احتياطي أخير لو yfinance ما رجّع إغلاق رسمي: أقرب شمعة من يوم تداول مختلف عن آخر شمعة
        last_date = pd_to_date(hist.index[-1])
        prior_rows = [row for idx, row in hist.iterrows() if pd_to_date(idx) != last_date]
        prev_close = float(prior_rows[-1]["Close"]) if prior_rows else float(last["Open"])

    change = float(last["Close"] - prev_close)
    change_pct = float((change / prev_close) * 100) if prev_close else 0.0

    return {
        "symbol": symbol,
        "timeframe": timeframe,
        "last_price": round(float(last["Close"]), 4),
        "change": round(change, 4),
        "change_pct": round(change_pct, 4),
        "open": round(float(last["Open"]), 4),
        "high": round(float(hist["High"].max()), 4),
        "low": round(float(hist["Low"].min()), 4),
        "candles": candles,
        "fetched_at": datetime.now(timezone.utc).isoformat(),
    }


def pd_isna(value) -> bool:
    try:
        return value != value  # NaN check بدون استيراد pandas مباشرة هون
    except Exception:
        return False


def pd_to_date(idx):
    """يرجع تاريخ (بدون وقت) من index الشمعة، يشتغل مع أي كائن فيه .date()."""
    try:
        return idx.date()
    except Exception:
        return str(idx)[:10]


def fetch_all(timeframe: str = "1D"):
    """يجلب كل الرموز المعرفة في config.py."""
    results = {}
    for name, symbol in ALL_SYMBOLS.items():
        try:
            data = fetch_ohlcv(symbol, timeframe)
            if data:
                results[name] = data
            else:
                print(f"[WARN] لا يوجد بيانات لـ {name} ({symbol})")
        except Exception as e:
            print(f"[ERROR] فشل جلب {name} ({symbol}): {e}")
    return results


def save_snapshot(data: dict, timeframe: str = "1D"):
    out_dir = os.path.join(OUTPUT_DIR, "prices")
    os.makedirs(out_dir, exist_ok=True)
    path = os.path.join(out_dir, f"snapshot_{timeframe}.json")
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    print(f"[OK] تم حفظ {path}")


if __name__ == "__main__":
    snapshot = fetch_all(timeframe="1D")
    save_snapshot(snapshot, timeframe="1D")

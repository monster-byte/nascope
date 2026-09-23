"""
AUREX AI - Data Layer Config
رموز yfinance المطابقة للوحة AUREX AI
"""

# المؤشر الرئيسي + العقود الآجلة
NASDAQ_100_INDEX = "^NDX"      # NASDAQ-100 Index (spot)
NASDAQ_FUTURES = "NQ=F"        # NQ1! - E-mini Nasdaq-100 Futures (CME)

# أكبر الأسهم المؤثرة (Market Drivers panel)
MEGA_CAPS = {
    "AAPL": "AAPL",
    "MSFT": "MSFT",
    "NVDA": "NVDA",
    "AMZN": "AMZN",
}

# مؤشرات مرتبطة (Market Drivers / Macro panel)
RELATED_INSTRUMENTS = {
    "VXN": "^VXN",       # Nasdaq Volatility Index
    "US10Y": "^TNX",     # US 10-Year Treasury Yield (÷10 للنسبة الفعلية)
    "DXY": "DX-Y.NYB",   # US Dollar Index
}

# كل الرموز المطلوب سحبها في كل دورة
ALL_SYMBOLS = {
    "NASDAQ_100_INDEX": NASDAQ_100_INDEX,
    "NASDAQ_FUTURES": NASDAQ_FUTURES,
    **MEGA_CAPS,
    **RELATED_INSTRUMENTS,
}

# مصدر التقويم الاقتصادي (Forex Factory - JSON عام غير رسمي)
FF_CALENDAR_URL_THIS_WEEK = "https://nfs.faireconomy.media/ff_calendar_thisweek.json"

# الفريمات الزمنية المدعومة بالداشبورد (1D, 5D, 1M, 3M, 6M, YTD, 1Y)
TIMEFRAME_MAP = {
    "1D": {"period": "5d", "interval": "5m"},
    "5D": {"period": "5d", "interval": "15m"},
    "1M": {"period": "1mo", "interval": "1h"},
    "3M": {"period": "3mo", "interval": "1d"},
    "6M": {"period": "6mo", "interval": "1d"},
    "YTD": {"period": "ytd", "interval": "1d"},
    "1Y": {"period": "1y", "interval": "1d"},
    # مخصص لمحرك Pulse (Micro Volume Profile) — دقة 1 دقيقة، آخر يومين بس
    # (yfinance يحدد بيانات الدقيقة الواحدة بحد أقصى 7 أيام، فترة يومين كافية
    # ومنخفضة المخاطر لأغراض السكالب اللي محتاجة بس آخر ساعة تقريباً)
    "1m": {"period": "2d", "interval": "1m"},
}

OUTPUT_DIR = "data"

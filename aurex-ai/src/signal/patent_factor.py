"""
AUREX AI - Patent Filing Momentum Factor
يقيس سرعة تسجيل براءات الاختراع لكبرى شركات التكنولوجيا (Mega-Caps) كمؤشر استباقي
لنشاط الابتكار والبحث والتطوير، بمقارنة عدد الطلبات المسجلة آخر 90 يوم بالفترة
الـ90 يوم اللي قبلها. زخم أعلى بالتسجيل = عامل صعودي (Bullish) للمؤشر.

المصدر: USPTO Open Data Portal (ODP) الرسمي - بيانات حكومية مفتوحة ومجانية.
يحتاج متغير بيئة USPTO_API_KEY (مفتاح مجاني، يتطلب حساب USPTO.gov موثّق عبر ID.me)
احصل عليه من: https://data.uspto.gov/myodp

⚠️ ملاحظة مهمة: هذا العامل لا يعتمد إطلاقاً على سحب بيانات (scraping) من LinkedIn
أو أي منصة تواصل اجتماعي. LinkedIn تمنع صراحة الجمع الآلي لبياناتها بشروط
الاستخدام، لذلك تم الاعتماد حصراً على مصدر USPTO الحكومي الرسمي والمجاني الذي
يوفر نفس الإشارة الاستباقية (نشاط الابتكار) بدون أي مخاطرة قانونية.
"""

import os
from datetime import datetime, timedelta

import requests

USPTO_SEARCH_URL = "https://api.uspto.gov/api/v1/patent/applications/search"


def _status_from_score(score: float) -> str:
    if score >= 65:
        return "green"
    if score >= 40:
        return "yellow"
    return "red"


# أسماء الشركات كما تُسجَّل رسمياً كـ Assignee في طلبات براءات USPTO
# (غالباً تختلف عن رمز السهم أو الاسم التجاري المعروف)
ASSIGNEE_NAMES = {
    "AAPL": "Apple Inc.",
    "MSFT": "Microsoft Technology Licensing, LLC",
    "NVDA": "Nvidia Corporation",
    "AMZN": "Amazon Technologies, Inc.",
}

LOOKBACK_DAYS = 90


def _count_filings(api_key: str, assignee: str, start: str, end: str) -> int:
    """يرجع عدد طلبات البراءات المسجلة باسم الشركة خلال فترة زمنية محددة."""
    headers = {"X-API-KEY": api_key}
    params = {
        "q": f'applicationMetaData.firstNamedApplicant:"{assignee}" '
             f'AND applicationMetaData.filingDate:[{start} TO {end}]',
        "limit": 1,  # يهمنا فقط العدد الكلي (count) اللي بيرجع مع كل استجابة، مو التفاصيل
    }
    resp = requests.get(USPTO_SEARCH_URL, headers=headers, params=params, timeout=20)
    resp.raise_for_status()
    data = resp.json()
    return int(data.get("count", 0))


def compute_patent_factor() -> dict:
    api_key = os.environ.get("USPTO_API_KEY")
    if not api_key:
        return {
            "factor": "patent_momentum",
            "score": 50.0,
            "status": "yellow",
            "details": {
                "error": "USPTO_API_KEY not set — تم استخدام قيمة محايدة افتراضية. "
                         "احصل على مفتاح مجاني من https://data.uspto.gov/myodp"
            },
        }

    today = datetime.utcnow().date()
    recent_start = today - timedelta(days=LOOKBACK_DAYS)
    prior_start = today - timedelta(days=LOOKBACK_DAYS * 2)

    per_company = {}
    total_recent, total_prior = 0, 0
    errors = []

    for symbol, assignee in ASSIGNEE_NAMES.items():
        try:
            recent_count = _count_filings(api_key, assignee, recent_start.isoformat(), today.isoformat())
            prior_count = _count_filings(api_key, assignee, prior_start.isoformat(), recent_start.isoformat())
        except Exception as e:
            errors.append(f"{symbol}: {e}")
            continue

        if prior_count > 0:
            momentum = recent_count / prior_count
        else:
            momentum = 2.0 if recent_count > 0 else 1.0  # ما في نشاط سابق للمقارنة عليه

        per_company[symbol] = {
            "recent_90d_filings": recent_count,
            "prior_90d_filings": prior_count,
            "momentum_ratio": round(momentum, 2),
        }
        total_recent += recent_count
        total_prior += prior_count

    if not per_company:
        return {
            "factor": "patent_momentum",
            "score": 50.0,
            "status": "yellow",
            "details": {"error": "patent_fetch_failed", "errors": errors},
        }

    overall_momentum = (total_recent / total_prior) if total_prior > 0 else 1.0
    # نحوّل نسبة الزخم لمقياس 0-100 حول نقطة الحياد 50 (زخم = 1.0 يعني بدون تغيير)
    score = 50 + (overall_momentum - 1.0) * 50
    score = max(0.0, min(100.0, round(score, 2)))

    return {
        "factor": "patent_momentum",
        "score": score,
        "status": _status_from_score(score),
        "details": {
            "lookback_days": LOOKBACK_DAYS,
            "total_recent_filings": total_recent,
            "total_prior_filings": total_prior,
            "overall_momentum_ratio": round(overall_momentum, 2),
            "per_company": per_company,
            "errors": errors or None,
        },
    }

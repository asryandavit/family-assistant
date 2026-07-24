"""Currency normalization to USD.

Live ECB rates via frankfurter.app (free, keyless), cached per process.
If the fetch fails, a static fallback table keeps the pipeline running --
slightly stale rates beat a dead run. Unknown codes return None and the
caller keeps the original price unconverted.
"""
import requests

# USD per one unit of currency (fallback only; live rates preferred)
FALLBACK = {
    "USD": 1.0, "EUR": 1.09, "GBP": 1.27, "CHF": 1.12,
    "HUF": 0.0028, "CZK": 0.044, "RON": 0.22, "PLN": 0.25,
    "BGN": 0.56, "SEK": 0.095, "NOK": 0.093, "DKK": 0.146,
    "AED": 0.27, "ILS": 0.27, "TRY": 0.03, "RSD": 0.0093,
    "MKD": 0.0177, "ALL": 0.0107, "GEL": 0.37, "AMD": 0.0026,
}

_rates = None


def _load():
    global _rates
    if _rates is not None:
        return _rates
    try:
        r = requests.get("https://api.frankfurter.app/latest?from=USD",
                         timeout=15).json()
        _rates = {c: 1.0 / v for c, v in (r.get("rates") or {}).items() if v}
        _rates["USD"] = 1.0
        print(f"  fx: live rates loaded ({len(_rates)} currencies)")
    except Exception as e:
        _rates = {}
        print(f"  fx: live rates unavailable ({str(e)[:60]}), using fallback")
    for c, v in FALLBACK.items():
        _rates.setdefault(c, v)
    return _rates


def to_usd(amount, code):
    """Convert to USD. None if amount is None or the code is unknown."""
    if amount is None:
        return None
    code = (code or "USD").upper()
    rate = _load().get(code)
    return round(float(amount) * rate, 2) if rate else None

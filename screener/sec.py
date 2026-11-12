"""Acceso a la API gratuita de la SEC (EDGAR / XBRL).

- universe(): todas las empresas con ticker registradas en la SEC.
- frame(): un dato concreto (p. ej. las ventas de 2024) para TODAS las empresas en una sola llamada.

La SEC pide identificarse con un User-Agent «Nombre email» y no superar 10 peticiones por segundo.
"""
from __future__ import annotations

import gzip
import json
import os
import threading
import time
from pathlib import Path

import requests

CACHE_DIR = Path(os.environ.get("SCREENER_CACHE", Path(__file__).resolve().parent.parent / "data" / "cache"))
CACHE_DIR.mkdir(parents=True, exist_ok=True)

DEFAULT_UA = "Screener publico screener@users.noreply.github.com"

_lock = threading.Lock()
_last_call = [0.0]


def _user_agent() -> str:
    return os.environ.get("SEC_USER_AGENT") or DEFAULT_UA


def _get(url: str, timeout: int = 60) -> requests.Response:
    with _lock:  # máximo ~8 peticiones por segundo
        wait = 0.12 - (time.time() - _last_call[0])
        if wait > 0:
            time.sleep(wait)
        _last_call[0] = time.time()
    r = requests.get(url, headers={"User-Agent": _user_agent(), "Accept-Encoding": "gzip, deflate"}, timeout=timeout)
    r.raise_for_status()
    return r


def _cached_json(name: str, url: str, max_age_h: float) -> dict:
    path = CACHE_DIR / f"{name}.json.gz"
    if path.exists() and (time.time() - path.stat().st_mtime) < max_age_h * 3600:
        with gzip.open(path, "rt", encoding="utf-8") as f:
            return json.load(f)
    data = _get(url).json()
    with gzip.open(path, "wt", encoding="utf-8") as f:
        json.dump(data, f)
    return data


def universe(max_age_h: float = 24) -> list[dict]:
    """Lista de empresas: cik, name, ticker, exchange."""
    raw = _cached_json("universe", "https://www.sec.gov/files/company_tickers_exchange.json", max_age_h)
    return [dict(zip(raw["fields"], row)) for row in raw["data"]]


def frame(tag: str, period: str, unit: str = "USD", taxonomy: str = "us-gaap", max_age_h: float = 24 * 7) -> dict[int, float]:
    """{cik: valor} para todas las empresas. period: 'CY2024' (anual) o 'CY2024Q4I' (saldo a cierre)."""
    try:
        raw = _cached_json(f"frame_{taxonomy}_{tag}_{unit.replace('/', '-')}_{period}",
                           f"https://data.sec.gov/api/xbrl/frames/{taxonomy}/{tag}/{unit}/{period}.json", max_age_h)
    except requests.HTTPError:
        return {}
    return {int(x["cik"]): float(x["val"]) for x in raw.get("data", [])}

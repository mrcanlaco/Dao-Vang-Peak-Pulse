"""CoinMarketCap client synced with Binance official CMC endpoints.

This module provides authoritative CoinMarketCap data (Market Cap, Name, Slug,
Rank, and URL) for Binance-listed futures and spot assets without requiring an
API key. It uses Binance's composite promo CoinMarketCap endpoints, which are
directly synced with both Binance and CoinMarketCap.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import httpx

from dao_vang.logging import get_logger

logger = get_logger(__name__)

_PROMO_QUOTES_PATH = "/bapi/composite/v1/public/promo/cmc/cryptocurrency/quotes/latest"
_PROMO_MAP_PATH = "/bapi/composite/v1/public/promo/cmc/cryptocurrency/map"
_DEFAULT_BASE_URL = "https://www.binance.com"
_DEFAULT_TIMEOUT_SECONDS = 10.0
_USER_AGENT = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"

_MULTIPLIERS = ("1000000", "100000", "10000", "1000")
_SETTLEMENTS = ("USDT", "BUSD", "USDC", "PERP")
_SYMBOL_ALIASES: dict[str, str] = {
    "1MBABYDOGE": "BABYDOGE",
    "RONIN": "RON",
    "VELODROME": "VELO",
    "DODOX": "DODO",
    "BEAMX": "BEAM",
    "LUNA2": "LUNA",
    "1000CAT": "CAT",
    "1000SATS": "SATS",
    "1000RATS": "RATS",
    "1000CHEEMS": "CHEEMS",
    "1000WHY": "WHY",
    "1000X": "X",
    "1000LUNC": "LUNC",
}

# Cache for static slug mapping
_SLUG_MAP: dict[str, dict[str, Any]] | None = None


@dataclass(frozen=True)
class CoinMarketCapData:
    """Market metadata and metrics from CoinMarketCap."""

    symbol: str
    clean_symbol: str
    name: str
    slug: str
    market_cap_usd: float | None
    price_usd: float | None
    cmc_rank: int | None
    cmc_url: str


def clean_symbol(symbol: str) -> str:
    """Normalize exchange symbol to standard CMC ticker."""
    s = str(symbol or "").upper().strip()
    for settlement in _SETTLEMENTS:
        if s.endswith(settlement):
            s = s[: -len(settlement)]
            break
    for mult in _MULTIPLIERS:
        if s.startswith(mult):
            s = s[len(mult) :]
            break
    return _SYMBOL_ALIASES.get(s, s)


def _load_slug_map() -> dict[str, dict[str, Any]]:
    """Load local pre-generated slug mapping file with fallback."""
    global _SLUG_MAP
    if _SLUG_MAP is not None:
        return _SLUG_MAP

    map_path = Path(__file__).resolve().parent.parent / "cmc_slug_map.json"
    if not map_path.exists():
        # Look in src/dao_vang/data/cmc_slug_map.json
        map_path = Path(__file__).resolve().parent.parent.parent / "dao_vang" / "data" / "cmc_slug_map.json"
    if map_path.exists():
        try:
            with open(map_path, "r", encoding="utf-8") as f:
                _SLUG_MAP = json.load(f)
                return _SLUG_MAP
        except Exception as exc:
            logger.warning("cmc_slug_map_load_failed", error=str(exc))

    _SLUG_MAP = {}
    return _SLUG_MAP


def resolve_token_meta(symbol: str) -> dict[str, Any]:
    """Resolve token name, slug, and CoinMarketCap URL offline or from cache."""
    s = str(symbol or "").upper().strip()
    slug_map = _load_slug_map()

    # 1. Exact match (e.g. CVCUSDT or CVC)
    if s in slug_map:
        return dict(slug_map[s])

    # 2. Cleaned symbol match
    cleaned = clean_symbol(s)
    if cleaned in slug_map:
        return dict(slug_map[cleaned])

    # 3. Fallback: standard lowercase slug
    slug = cleaned.lower()
    return {
        "slug": slug,
        "name": cleaned,
        "cmc_url": f"https://coinmarketcap.com/currencies/{slug}/",
        "rank": None,
        "id": None,
    }


def _select_best_token(tokens: list[dict[str, Any]]) -> dict[str, Any] | None:
    """Select the best matching token among multiple CMC results."""
    if not tokens:
        return None

    def _rank_key(it: dict[str, Any]) -> tuple[int, bool, int, float]:
        active = 1 if it.get("is_active") == 1 else 0
        quote_usd = it.get("quote", {}).get("USD", {}) if isinstance(it.get("quote"), dict) else {}
        mcap = float(quote_usd.get("market_cap") or 0.0)
        cmc_rank = it.get("cmc_rank")
        rank_score = -cmc_rank if cmc_rank is not None else -999999999
        return (active, mcap > 0, rank_score, mcap)

    return max(tokens, key=_rank_key)


def fetch_market_data(
    symbol: str,
    config: Any = None,
) -> CoinMarketCapData | None:
    """Fetch market data for a symbol from Binance CMC endpoint."""
    cleaned = clean_symbol(symbol)
    if not cleaned:
        return None

    base_url = getattr(config, "base_url", _DEFAULT_BASE_URL) if config else _DEFAULT_BASE_URL
    timeout = getattr(config, "timeout_seconds", _DEFAULT_TIMEOUT_SECONDS) if config else _DEFAULT_TIMEOUT_SECONDS

    url = f"{base_url.rstrip('/')}{_PROMO_QUOTES_PATH}"
    params = {"symbol": cleaned}
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }

    try:
        with httpx.Client(timeout=timeout, headers=headers) as client:
            resp = client.get(url, params=params)
            resp.raise_for_status()
            payload = resp.json()
    except Exception as exc:
        logger.warning("cmc_quotes_fetch_failed", symbol=symbol, error=str(exc))
        meta = resolve_token_meta(symbol)
        slug = meta.get("slug") or cleaned.lower()
        return CoinMarketCapData(
            symbol=symbol,
            clean_symbol=cleaned,
            name=meta.get("name") or cleaned,
            slug=slug,
            market_cap_usd=None,
            price_usd=None,
            cmc_rank=meta.get("rank"),
            cmc_url=meta.get("cmc_url") or f"https://coinmarketcap.com/currencies/{slug}/",
        )

    body_data = payload.get("data", {}).get("body", {}).get("data", {})
    tokens = body_data.get(cleaned, [])
    best = _select_best_token(tokens)

    if not best:
        meta = resolve_token_meta(symbol)
        slug = meta.get("slug") or cleaned.lower()
        return CoinMarketCapData(
            symbol=symbol,
            clean_symbol=cleaned,
            name=meta.get("name") or cleaned,
            slug=slug,
            market_cap_usd=None,
            price_usd=None,
            cmc_rank=meta.get("rank"),
            cmc_url=meta.get("cmc_url") or f"https://coinmarketcap.com/currencies/{slug}/",
        )

    slug = best.get("slug") or cleaned.lower()
    quote_usd = best.get("quote", {}).get("USD", {}) if isinstance(best.get("quote"), dict) else {}
    mcap = quote_usd.get("market_cap")
    mcap_usd = float(mcap) if mcap is not None and float(mcap) > 0 else None
    price = quote_usd.get("price")
    price_usd = float(price) if price is not None and float(price) > 0 else None

    return CoinMarketCapData(
        symbol=symbol,
        clean_symbol=cleaned,
        name=best.get("name") or cleaned,
        slug=slug,
        market_cap_usd=mcap_usd,
        price_usd=price_usd,
        cmc_rank=best.get("cmc_rank"),
        cmc_url=f"https://coinmarketcap.com/currencies/{slug}/",
    )


def batch_fetch_market_data(
    symbols: list[str],
    config: Any = None,
    chunk_size: int = 30,
) -> dict[str, CoinMarketCapData]:
    """Fetch market data for multiple symbols in batch."""
    if not symbols:
        return {}

    base_url = getattr(config, "base_url", _DEFAULT_BASE_URL) if config else _DEFAULT_BASE_URL
    timeout = getattr(config, "timeout_seconds", _DEFAULT_TIMEOUT_SECONDS) if config else _DEFAULT_TIMEOUT_SECONDS

    cleaned_to_orig: dict[str, list[str]] = {}
    for s in symbols:
        c = clean_symbol(s)
        if c:
            cleaned_to_orig.setdefault(c, []).append(s)

    unique_cleaned = list(cleaned_to_orig.keys())
    results: dict[str, CoinMarketCapData] = {}
    url = f"{base_url.rstrip('/')}{_PROMO_QUOTES_PATH}"
    headers = {
        "User-Agent": _USER_AGENT,
        "Accept": "application/json",
    }

    with httpx.Client(timeout=timeout, headers=headers) as client:
        for i in range(0, len(unique_cleaned), chunk_size):
            chunk = unique_cleaned[i : i + chunk_size]
            query_str = ",".join(chunk)
            try:
                resp = client.get(url, params={"symbol": query_str})
                resp.raise_for_status()
                payload = resp.json()
                body_data = payload.get("data", {}).get("body", {}).get("data", {})
            except Exception as exc:
                logger.warning("cmc_batch_quotes_failed", chunk=chunk, error=str(exc))
                body_data = {}

            for clean_sym in chunk:
                orig_symbols = cleaned_to_orig.get(clean_sym, [])
                tokens = body_data.get(clean_sym, [])
                best = _select_best_token(tokens)

                if best:
                    slug = best.get("slug") or clean_sym.lower()
                    quote_usd = best.get("quote", {}).get("USD", {}) if isinstance(best.get("quote"), dict) else {}
                    mcap = quote_usd.get("market_cap")
                    mcap_usd = float(mcap) if mcap is not None and float(mcap) > 0 else None
                    price = quote_usd.get("price")
                    price_usd = float(price) if price is not None and float(price) > 0 else None
                    data = CoinMarketCapData(
                        symbol=orig_symbols[0] if orig_symbols else clean_sym,
                        clean_symbol=clean_sym,
                        name=best.get("name") or clean_sym,
                        slug=slug,
                        market_cap_usd=mcap_usd,
                        price_usd=price_usd,
                        cmc_rank=best.get("cmc_rank"),
                        cmc_url=f"https://coinmarketcap.com/currencies/{slug}/",
                    )
                else:
                    meta = resolve_token_meta(clean_sym)
                    slug = meta.get("slug") or clean_sym.lower()
                    data = CoinMarketCapData(
                        symbol=orig_symbols[0] if orig_symbols else clean_sym,
                        clean_symbol=clean_sym,
                        name=meta.get("name") or clean_sym,
                        slug=slug,
                        market_cap_usd=None,
                        price_usd=None,
                        cmc_rank=meta.get("rank"),
                        cmc_url=meta.get("cmc_url") or f"https://coinmarketcap.com/currencies/{slug}/",
                    )

                for orig in orig_symbols:
                    results[orig] = data

    return results


def fetch_market_cap(symbol: str, config: Any = None) -> float | None:
    """Fetch market cap in USD for a token."""
    data = fetch_market_data(symbol, config)
    return data.market_cap_usd if data else None

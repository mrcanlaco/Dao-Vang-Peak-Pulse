"""Binance Agent OS token-information client.

The Binance Skills Hub ``query-token-info`` search endpoint returns a
Binance-standard ``marketCap`` value for a token search result.  This module
keeps the integration read-only and intentionally uses the search response so
the dashboard can resolve a futures symbol without storing chain-specific
contract addresses.

Official skill:
https://www.binance.com/en/skills/detail/binance-web3/query-token-info
"""

from __future__ import annotations

from typing import Any, cast

import httpx

from dao_vang.config.settings import BinanceAgentOSConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)

_TOKEN_SEARCH_PATH = (
    "/bapi/defi/v5/public/wallet-direct/buw/wallet/market/token/search/ai"
)


def _clean_symbol(symbol: str) -> str:
    return (
        str(symbol or "")
        .upper()
        .replace("USDT", "")
        .replace("BUSD", "")
        .replace("USDC", "")
        .replace("PERP", "")
        .strip()
    )


def _positive_float(value: Any) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _search_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract token rows from the Agent OS response envelope."""
    data = payload.get("data")
    if isinstance(data, list):
        return [row for row in data if isinstance(row, dict)]
    if isinstance(data, dict):
        for key in ("list", "items", "tokens", "data"):
            rows = data.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)]
    return []


def fetch_market_cap(symbol: str, config: BinanceAgentOSConfig) -> float | None:
    """Fetch a token's Binance Agent OS market cap in USD.

    Search results encode numeric market fields as strings.  Exact symbol
    matches are preferred because a keyword search can return similarly named
    tokens from multiple supported chains.  ``None`` means that Binance did
    not return a positive market cap or the public endpoint was unavailable.
    """
    if not config.enabled:
        return None

    clean_symbol = _clean_symbol(symbol)
    if not clean_symbol:
        return None

    try:
        with httpx.Client(
            timeout=config.timeout_seconds,
            headers={
                "Accept-Encoding": "identity",
                "User-Agent": "dao-vang/binance-agent-os",
            },
        ) as client:
            response = client.get(
                f"{config.base_url.rstrip('/')}{_TOKEN_SEARCH_PATH}",
                params={
                    "keyword": clean_symbol,
                    "chainIds": config.chain_ids,
                    "orderBy": "volume24h",
                },
            )
            if response.status_code == 404:
                logger.debug(
                    "binance_agent_os_market_cap_not_found",
                    symbol=symbol,
                )
                return None
            response.raise_for_status()
            raw_payload = response.json()
            if not isinstance(raw_payload, dict):
                return None
            payload = cast(dict[str, Any], raw_payload)
    except (httpx.HTTPError, OSError, TypeError, ValueError) as exc:
        logger.warning(
            "binance_agent_os_market_cap_fetch_failed",
            symbol=symbol,
            error=str(exc),
        )
        return None

    code = payload.get("code")
    if code is not None and str(code) not in {"0", "000000"}:
        logger.debug(
            "binance_agent_os_market_cap_business_error",
            symbol=symbol,
            code=code,
        )
        return None

    rows = _search_rows(payload)
    exact_matches: list[float] = []
    for row in rows:
        market_cap = _positive_float(
            row.get("marketCap", row.get("market_cap"))
        )
        if market_cap is None:
            continue
        row_symbol = _clean_symbol(str(row.get("symbol", "")))
        if row_symbol == clean_symbol:
            exact_matches.append(market_cap)

    # Never assign a similarly named token's market cap to the requested
    # symbol. If Binance Agent OS has no exact result, the API layer produces
    # a clearly labelled local estimate instead.
    if exact_matches:
        return exact_matches[0]
    return None

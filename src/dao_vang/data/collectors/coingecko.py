"""CoinGecko client — multi-source cross-reference for price/volume.

Free API, no key required. Rate limit: ~10-30 req/min on free tier.
Used to cross-validate Binance data and detect exchange manipulation.

https://www.coingecko.com/api/documentation
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, cast

import httpx

from dao_vang.config.settings import CoinGeckoConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)


@dataclass(frozen=True)
class CoinGeckoMarketData:
    """Market data from CoinGecko for a single coin."""

    coingecko_id: str
    symbol: str  # lowercase, e.g. "btc"
    current_price_usd: float
    total_volume_usd: float
    market_cap_usd: float
    price_change_24h_pct: float
    price_change_7d_pct: float


@dataclass(frozen=True)
class CrossReferenceReport:
    """Result of cross-referencing Binance vs CoinGecko data."""

    binance_price: float
    coingecko_price: float | None
    price_diff_pct: float | None  # |binance - coingecko| / coingecko
    volume_diff_pct: float | None
    flag: str  # "OK" | "PRICE_MISMATCH" | "NO_COINGECKO_DATA" | "DISABLED"
    explanation: str


def _symbol_to_coingecko_id(symbol: str) -> str:
    """Convert trading symbol to CoinGecko coin id.

    For USDT pairs: BTCUSDT → btc, ETHUSDT → eth, etc.
    Falls back to lowercase symbol if no mapping.
    """
    # Strip USDT suffix
    base = symbol.replace("USDT", "").replace("USD", "").lower()
    # Common mappings (CoinGecko uses specific IDs)
    mapping: dict[str, str] = {
        "btc": "bitcoin",
        "eth": "ethereum",
        "sol": "solana",
        "bnb": "binancecoin",
        "xrp": "ripple",
        "ada": "cardano",
        "doge": "dogecoin",
        "avax": "avalanche-2",
        "dot": "polkadot",
        "matic": "matic-network",
        "link": "chainlink",
        "ltc": "litecoin",
        "atom": "cosmos",
        "uni": "uniswap",
        "arb": "arbitrum",
        "op": "optimism",
        "apt": "aptos",
        "near": "near",
        "fil": "filecoin",
        "ftm": "fantom",
        "sand": "the-sandbox",
        "mana": "decentraland",
        "axs": "axie-infinity",
        "sushi": "sushi",
        "aave": "aave",
        "snx": "havven",
        "comp": "compound-governance-token",
        "dydx": "dydx-chain",
        "pepe": "pepe",
        "shib": "shiba-inu",
        "floki": "floki",
        "wif": "dogwifcoin",
        "bome": "book-of-meme",
        "bonk": "bonk",
        "jup": "jupiter-exchange-solana",
        "pyth": "pyth-network",
        "jto": "jito-governance-token",
        "tia": "celestia",
        "sei": "seismic-3",
        "sui": "sui",
        "ton": "the-open-network",
    }
    return mapping.get(base, base)


def fetch_market_data(
    symbol: str,
    config: CoinGeckoConfig,
) -> CoinGeckoMarketData | None:
    """Fetch market data for a symbol from CoinGecko.

    Args:
        symbol: Trading symbol (e.g. "BTCUSDT").
        config: CoinGeckoConfig with base_url + timeout.

    Returns CoinGeckoMarketData or None on error.
    """
    if not config.enabled:
        return None

    coin_id = _symbol_to_coingecko_id(symbol)
    try:
        with httpx.Client(timeout=config.timeout_seconds) as client:
            resp = client.get(
                f"{config.base_url}/coins/{coin_id}",
                params={
                    "localization": "false",
                    "tickers": "false",
                    "market_data": "true",
                    "community_data": "false",
                    "developer_data": "false",
                    "sparkline": "false",
                },
            )
            if resp.status_code == 404:
                logger.debug("coingecko_not_found", symbol=symbol, coin_id=coin_id)
                return None
            resp.raise_for_status()
            data = cast(dict[str, Any], resp.json())
    except (httpx.HTTPError, OSError) as exc:
        logger.warning("coingecko_fetch_failed", symbol=symbol, error=str(exc))
        return None

    md = data.get("market_data", {})
    base_symbol = symbol.replace("USDT", "").lower()
    return CoinGeckoMarketData(
        coingecko_id=coin_id,
        symbol=base_symbol,
        current_price_usd=float(md.get("current_price", {}).get("usd", 0)),
        total_volume_usd=float(md.get("total_volume", {}).get("usd", 0)),
        market_cap_usd=float(md.get("market_cap", {}).get("usd", 0)),
        price_change_24h_pct=float(md.get("price_change_percentage_24h", 0) or 0),
        price_change_7d_pct=float(md.get("price_change_percentage_7d", 0) or 0),
    )


def cross_reference(
    binance_price: float,
    binance_volume_usd: float,
    symbol: str,
    config: CoinGeckoConfig,
) -> CrossReferenceReport:
    """Cross-reference Binance price/volume with CoinGecko.

    Args:
        binance_price: Latest close price from Binance.
        binance_volume_usd: 24h quote volume from Binance.
        symbol: Trading symbol (e.g. "BTCUSDT").
        config: CoinGeckoConfig.

    Returns CrossReferenceReport with mismatch flag if any.
    """
    if not config.enabled:
        return CrossReferenceReport(
            binance_price=binance_price,
            coingecko_price=None,
            price_diff_pct=None,
            volume_diff_pct=None,
            flag="DISABLED",
            explanation="CoinGecko cross-reference disabled in config.",
        )

    cg_data = fetch_market_data(symbol, config)
    if cg_data is None or cg_data.current_price_usd <= 0:
        return CrossReferenceReport(
            binance_price=binance_price,
            coingecko_price=None,
            price_diff_pct=None,
            volume_diff_pct=None,
            flag="NO_COINGECKO_DATA",
            explanation=f"No CoinGecko data for {symbol} — cannot cross-reference.",
        )

    price_diff = (
        abs(binance_price - cg_data.current_price_usd) / cg_data.current_price_usd
    )
    volume_diff = (
        abs(binance_volume_usd - cg_data.total_volume_usd) / cg_data.total_volume_usd
        if cg_data.total_volume_usd > 0
        else None
    )

    if price_diff > config.price_mismatch_threshold:
        flag = "PRICE_MISMATCH"
        explanation = (
            f"Binance price {binance_price} vs CoinGecko "
            f"{cg_data.current_price_usd} — diff {price_diff:.1%} "
            f"(threshold {config.price_mismatch_threshold:.0%}). "
            f"Possible exchange manipulation."
        )
    else:
        flag = "OK"
        explanation = (
            f"Binance vs CoinGecko price diff {price_diff:.1%} — within tolerance."
        )

    logger.info(
        "coingecko_cross_ref",
        symbol=symbol,
        price_diff=price_diff,
        flag=flag,
    )
    return CrossReferenceReport(
        binance_price=binance_price,
        coingecko_price=cg_data.current_price_usd,
        price_diff_pct=price_diff,
        volume_diff_pct=volume_diff,
        flag=flag,
        explanation=explanation,
    )

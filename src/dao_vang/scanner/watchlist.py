"""Watchlist builder — merge manual watchlist + auto market scan.

Manual watchlist: persisted in watchlist.json (user-curated).
Auto market scan: fetched from Binance 24h ticker, filtered by volume +
price change, sorted by scan_mode, capped at max_coins.

Scan modes:
  - "gainers":  top coins tăng mạnh nhất 24h (ứng viên short chính)
  - "losers":   top coins giảm mạnh nhất 24h (đã xả, có thể short tiếp)
  - "volume":   top coins theo khối lượng giao dịch 24h
  - "volatile": top coins biến động mạnh (|price change| cao)
  - "all":      kết hợp gainers + losers + volume

De-dup: manual watchlist always included; auto fill remaining slots up
to max_coins. Stablecoins (USDT/USDC/DAI/TUSD/FDUSD/BUSD) excluded by
default. BTC always included if include_btc=True.
"""

from __future__ import annotations

import json
import math
import os
import threading
from pathlib import Path
from typing import Any, cast

import httpx

from dao_vang.config.settings import ScannerConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)

_WATCHLIST_LOCK = threading.RLock()

# Stablecoins to exclude (base symbols, uppercase)
_STABLECOIN_BASES = {
    "USDT", "USDC", "DAI", "TUSD", "FDUSD", "BUSD", "USDP",
    "EUR", "GBP", "TRY", "BRL", "ARS", "RUB",
}

_SUPPORTED_SCAN_MODES = frozenset(
    {"gainers", "losers", "volume", "volatile", "manual", "all"}
)


def normalize_scan_modes(value: object) -> list[str]:
    """Normalize a legacy mode or a list of modes into ordered mode IDs.

    The web UI persists ``scan_modes`` as a list, while older config/runtime
    files still use the singular ``scan_mode`` string.  Accept both formats so
    an upgrade does not reset a user's scanner selection.  ``all`` keeps its
    historical meaning and expands to gainers + losers + volume.
    """
    if isinstance(value, str):
        raw_modes: list[object] = value.split(",")
    elif isinstance(value, (list, tuple, set, frozenset)):
        raw_modes = list(value)
    else:
        raw_modes = []

    modes: list[str] = []
    seen: set[str] = set()
    for raw_mode in raw_modes:
        if not isinstance(raw_mode, str):
            continue
        mode = raw_mode.strip().lower()
        if not mode:
            continue
        expanded = ("gainers", "losers", "volume") if mode == "all" else (mode,)
        for item in expanded:
            if item in _SUPPORTED_SCAN_MODES and item != "all" and item not in seen:
                seen.add(item)
                modes.append(item)

    return modes or ["gainers"]


def _is_stablecoin(symbol: str) -> bool:
    """Check if symbol is a stablecoin pair (VD: USDCUSDT, BUSDUSDT)."""
    if not symbol.endswith("USDT"):
        return False
    base = symbol[:-4].upper()  # strip "USDT" suffix only
    return base in _STABLECOIN_BASES or base == ""


def load_manual_watchlist(path: Path) -> list[str]:
    """Load manual watchlist from JSON file.

    Returns empty list if file doesn't exist or is invalid.
    """
    if not path.exists():
        return []
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
        if isinstance(data, list):
            raw_list = cast(list[Any], data)
            items: list[str] = []
            seen: set[str] = set()
            for s in raw_list:
                if isinstance(s, str):
                    symbol = s.strip().upper()
                    if symbol and symbol not in seen:
                        seen.add(symbol)
                        items.append(symbol)
            return items
    except (json.JSONDecodeError, OSError) as exc:
        logger.warning("watchlist_load_failed", path=str(path), error=str(exc))
    return []


def save_manual_watchlist(path: Path, symbols: list[str]) -> None:
    """Save manual watchlist to JSON file."""
    cleaned: list[str] = []
    seen: set[str] = set()
    for symbol in symbols:
        normalized = str(symbol).strip().upper()
        if normalized and normalized not in seen:
            seen.add(normalized)
            cleaned.append(normalized)

    with _WATCHLIST_LOCK:
        path.parent.mkdir(parents=True, exist_ok=True)
        # Replace atomically so the scanner never reads a half-written JSON
        # file while a user is adding/removing a coin.
        temp_path = path.with_name(
            f".{path.name}.{os.getpid()}.{threading.get_ident()}.tmp"
        )
        temp_path.write_text(json.dumps(cleaned, indent=2), encoding="utf-8")
        temp_path.replace(path)


def add_to_watchlist(path: Path, symbol: str) -> list[str]:
    """Add a symbol to manual watchlist. Returns updated list."""
    with _WATCHLIST_LOCK:
        symbols = load_manual_watchlist(path)
        sym = symbol.strip().upper()
        if sym and sym not in symbols:
            symbols.append(sym)
            save_manual_watchlist(path, symbols)
            logger.info("watchlist_added", symbol=sym, total=len(symbols))
        return symbols


def remove_from_watchlist(path: Path, symbol: str) -> list[str]:
    """Remove a symbol from manual watchlist. Returns updated list."""
    with _WATCHLIST_LOCK:
        symbols = load_manual_watchlist(path)
        sym = symbol.strip().upper()
        if sym in symbols:
            symbols.remove(sym)
            save_manual_watchlist(path, symbols)
            logger.info("watchlist_removed", symbol=sym, total=len(symbols))
        return symbols


_TICKERS_CACHE: tuple[float, list[dict[str, Any]]] | None = None
_CACHE_TTL = 30.0  # 30 seconds TTL cache


def reset_tickers_cache() -> None:
    """Clear the tickers cache. Useful for testing."""
    global _TICKERS_CACHE
    _TICKERS_CACHE = None


def fetch_all_tickers(
    base_url: str = "https://fapi.binance.com",
    timeout: float = 15.0,
) -> list[dict[str, Any]]:
    """Fetch all 24h tickers from Binance USD-M futures with 30s RAM cache."""
    global _TICKERS_CACHE
    import time
    now = time.time()
    if _TICKERS_CACHE is not None:
        cached_time, cached_data = _TICKERS_CACHE
        if now - cached_time < _CACHE_TTL:
            return cached_data

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.get(f"{base_url}/fapi/v1/ticker/24hr")
            resp.raise_for_status()
            data = resp.json()
            res = [d for d in data if isinstance(d, dict) and d.get("symbol", "").endswith("USDT")]
            _TICKERS_CACHE = (now, res)
            return res
    except (httpx.HTTPError, OSError) as exc:
        logger.error("tickers_fetch_failed", error=str(exc))
        if _TICKERS_CACHE is not None:
            return _TICKERS_CACHE[1]
        return []


def _filter_tickers(
    tickers: list[dict[str, Any]],
    min_volume_usd: float,
    min_price_change_pct: float,
    exclude_stablecoins: bool,
) -> list[dict[str, Any]]:
    """Filter tickers by volume, price change, and stablecoin exclusion."""
    result: list[dict[str, Any]] = []
    for d in tickers:
        symbol = d.get("symbol", "")
        volume = float(d.get("quoteVolume", 0))
        change_pct = abs(float(d.get("priceChangePercent", 0)))
        if volume < min_volume_usd:
            continue
        if min_price_change_pct > 0 and change_pct < min_price_change_pct:
            continue
        if exclude_stablecoins and _is_stablecoin(symbol):
            continue
        result.append(d)
    return result


def fetch_top_gainers(
    base_url: str = "https://fapi.binance.com",
    min_volume_usd: float = 1_000_000,
    limit: int = 50,
    min_price_change_pct: float = 0.0,
    exclude_stablecoins: bool = True,
) -> list[dict[str, Any]]:
    """Fetch 24h tickers from Binance USD-M futures, sorted by gain.

    Args:
        base_url: Binance USD-M futures base URL.
        min_volume_usd: Minimum 24h quote volume filter.
        limit: Max number of tickers to return.
        min_price_change_pct: Minimum |price change %| filter (0 = no filter).
        exclude_stablecoins: Exclude stablecoin pairs.

    Returns list of ticker dicts sorted by priceChangePercent desc.
    """
    tickers = fetch_all_tickers(base_url)
    filtered = _filter_tickers(
        tickers, min_volume_usd, min_price_change_pct, exclude_stablecoins
    )
    filtered.sort(
        key=lambda x: float(x.get("priceChangePercent", 0)),
        reverse=True,
    )
    return filtered[:limit]


def fetch_top_losers(
    base_url: str = "https://fapi.binance.com",
    min_volume_usd: float = 1_000_000,
    limit: int = 50,
    min_price_change_pct: float = 0.0,
    exclude_stablecoins: bool = True,
) -> list[dict[str, Any]]:
    """Fetch 24h tickers sorted by loss (priceChangePercent asc).

    Useful for finding coins that already started dumping — potential
    short continuation candidates.
    """
    tickers = fetch_all_tickers(base_url)
    filtered = _filter_tickers(
        tickers, min_volume_usd, min_price_change_pct, exclude_stablecoins
    )
    filtered.sort(
        key=lambda x: float(x.get("priceChangePercent", 0)),
    )
    return filtered[:limit]


def fetch_top_volume(
    base_url: str = "https://fapi.binance.com",
    min_volume_usd: float = 1_000_000,
    limit: int = 50,
    min_price_change_pct: float = 0.0,
    exclude_stablecoins: bool = True,
) -> list[dict[str, Any]]:
    """Fetch 24h tickers sorted by quote volume (most traded first).

    High-volume coins are more liquid — safer to short, less slippage.
    """
    tickers = fetch_all_tickers(base_url)
    filtered = _filter_tickers(
        tickers, min_volume_usd, min_price_change_pct, exclude_stablecoins
    )
    filtered.sort(
        key=lambda x: float(x.get("quoteVolume", 0)),
        reverse=True,
    )
    return filtered[:limit]


def fetch_top_volatile(
    base_url: str = "https://fapi.binance.com",
    min_volume_usd: float = 1_000_000,
    limit: int = 50,
    min_price_change_pct: float = 0.0,
    exclude_stablecoins: bool = True,
) -> list[dict[str, Any]]:
    """Fetch 24h tickers sorted by absolute price change (most volatile).

    Volatile coins have more distribution events → better for AI training.
    """
    tickers = fetch_all_tickers(base_url)
    filtered = _filter_tickers(
        tickers, min_volume_usd, min_price_change_pct, exclude_stablecoins
    )
    filtered.sort(
        key=lambda x: abs(float(x.get("priceChangePercent", 0))),
        reverse=True,
    )
    return filtered[:limit]


def _fetch_by_mode(
    mode: str,
    config: ScannerConfig,
    base_url: str = "https://fapi.binance.com",
) -> list[dict[str, Any]]:
    """Fetch and merge tickers for one or more scan modes."""
    min_vol = config.min_volume_usd
    lim = config.max_coins * 2
    min_chg = config.min_price_change_pct
    excl_stable = config.exclude_stablecoins

    combined: list[dict[str, Any]] = []
    seen: set[str] = set()
    for selected_mode in normalize_scan_modes(mode):
        # Manual mode intentionally skips the automatic Binance shortlist. The
        # caller still merges the persisted manual symbols below.
        if selected_mode == "manual":
            continue
        if selected_mode == "losers":
            batch = fetch_top_losers(
                base_url=base_url, min_volume_usd=min_vol, limit=lim,
                min_price_change_pct=min_chg, exclude_stablecoins=excl_stable,
            )
        elif selected_mode == "volume":
            batch = fetch_top_volume(
                base_url=base_url, min_volume_usd=min_vol, limit=lim,
                min_price_change_pct=min_chg, exclude_stablecoins=excl_stable,
            )
        elif selected_mode == "volatile":
            batch = fetch_top_volatile(
                base_url=base_url, min_volume_usd=min_vol, limit=lim,
                min_price_change_pct=min_chg, exclude_stablecoins=excl_stable,
            )
        else:  # gainers
            batch = fetch_top_gainers(
                base_url=base_url, min_volume_usd=min_vol, limit=lim,
                min_price_change_pct=min_chg, exclude_stablecoins=excl_stable,
            )

        for ticker in batch:
            symbol = ticker.get("symbol", "")
            if symbol and symbol not in seen:
                seen.add(symbol)
                combined.append(ticker)
    return combined


def build_scan_list(config: ScannerConfig) -> list[str]:
    """Build the list of symbols to scan this cycle.

    Merges manual watchlist + auto market scan (by scan_mode), de-duped,
    capped at config.max_coins. Manual watchlist has priority.

    Args:
        config: ScannerConfig with watchlist_path, max_coins, min_volume_usd,
            scan_mode, min_price_change_pct, include_btc, exclude_stablecoins.

    Returns list of symbols (uppercase, de-duped).
    """
    manual = load_manual_watchlist(config.watchlist_path)
    auto_tickers = _fetch_by_mode(config.scan_mode, config)
    auto_symbols = [d["symbol"] for d in auto_tickers if "symbol" in d]

    # Merge with de-dup, manual first
    seen: set[str] = set()
    result: list[str] = []

    # Manual watchlist first (always included)
    for sym in manual:
        s = sym.upper()
        if s not in seen:
            seen.add(s)
            result.append(s)
        if len(result) >= config.max_coins:
            break

    # Then auto symbols
    for sym in auto_symbols:
        if len(result) >= config.max_coins:
            break
        s = sym.upper()
        if s not in seen:
            seen.add(s)
            result.append(s)

    # Ensure BTC is included (needed for BTC context scoring)
    if config.include_btc and "BTCUSDT" not in seen and len(result) < config.max_coins:
        result.append("BTCUSDT")
    elif config.include_btc and "BTCUSDT" not in seen and len(result) >= config.max_coins:
        # Replace last slot with BTC if BTC not in list
        result[-1] = "BTCUSDT"

    logger.info(
        "scan_list_built",
        scan_mode=config.scan_mode,
        manual_count=len(manual),
        auto_count=len(auto_symbols),
        total=len(result),
        min_change_pct=config.min_price_change_pct,
    )
    return result


def build_comparison_universe(
    config: ScannerConfig,
    *,
    pinned_symbols: list[str] | tuple[str, ...] = (),
    limit: int | None = None,
) -> list[dict[str, Any]]:
    """Build the shared, broad universe used to audit candidate filters.

    Production symbols are pinned first so the champion is always represented.
    Remaining slots mix high absolute 24h movement with high liquidity.  The
    comparison intentionally drops the production ``min_price_change_pct``
    gate: this lets us measure whether that initial gate misses future dumps,
    while keeping the same volume and stablecoin safety constraints.

    The returned ticker rows come from the same cached Binance 24h snapshot as
    ``build_scan_list`` whenever both functions run in one daemon cycle.
    """

    target = max(1, min(int(limit or config.max_coins), 500))
    tickers = fetch_all_tickers()
    eligible = _filter_tickers(
        tickers,
        config.min_volume_usd,
        0.0,
        config.exclude_stablecoins,
    )
    by_symbol = {
        str(item.get("symbol", "")).upper(): item
        for item in eligible
        if item.get("symbol")
    }

    selected: list[dict[str, Any]] = []
    seen: set[str] = set()

    def append_symbol(symbol: str) -> None:
        normalized = str(symbol).strip().upper()
        ticker = by_symbol.get(normalized)
        if ticker is None or normalized in seen or len(selected) >= target:
            return
        seen.add(normalized)
        selected.append(ticker)

    for symbol in pinned_symbols:
        append_symbol(symbol)

    # Use two independent rankings to avoid a universe made exclusively of
    # already-moving coins or exclusively of very large caps.
    by_movement = sorted(
        eligible,
        key=lambda item: abs(float(item.get("priceChangePercent", 0) or 0)),
        reverse=True,
    )
    by_volume = sorted(
        eligible,
        key=lambda item: float(item.get("quoteVolume", 0) or 0),
        reverse=True,
    )
    remaining = max(0, target - len(selected))
    movement_slots = int(math.ceil(remaining * 0.70))
    for item in by_movement:
        if movement_slots <= 0 or len(selected) >= target:
            break
        before = len(selected)
        append_symbol(str(item.get("symbol", "")))
        if len(selected) > before:
            movement_slots -= 1
    for item in by_volume:
        if len(selected) >= target:
            break
        append_symbol(str(item.get("symbol", "")))
    # If either ranking contained duplicates with pinned symbols, fill any
    # leftover capacity deterministically from movement rank.
    for item in by_movement:
        if len(selected) >= target:
            break
        append_symbol(str(item.get("symbol", "")))

    if config.include_btc and "BTCUSDT" in by_symbol and "BTCUSDT" not in seen:
        if len(selected) >= target:
            selected[-1] = by_symbol["BTCUSDT"]
        else:
            selected.append(by_symbol["BTCUSDT"])

    logger.info(
        "candidate_comparison_universe_built",
        pinned_count=len(tuple(pinned_symbols)),
        eligible_count=len(eligible),
        total=len(selected),
        target=target,
    )
    return selected


def preview_scan_list(config: ScannerConfig) -> dict[str, Any]:
    """Preview what the scanner would scan — for CLI/UI display.

    Returns dict with:
        scan_mode, manual_watchlist, auto_tickers (top 10 with details),
        final_list, total_count.
    """
    manual = load_manual_watchlist(config.watchlist_path)
    auto_tickers = _fetch_by_mode(config.scan_mode, config)
    final_list = build_scan_list(config)

    # Top 10 auto tickers with details for display
    auto_preview: list[dict[str, Any]] = []
    for d in auto_tickers[:10]:
        auto_preview.append({
            "symbol": d.get("symbol", ""),
            "change_pct": float(d.get("priceChangePercent", 0)),
            "volume_usd": float(d.get("quoteVolume", 0)),
            "last_price": float(d.get("lastPrice", 0)),
        })

    return {
        "scan_mode": config.scan_mode,
        "scan_modes": normalize_scan_modes(config.scan_mode),
        "min_volume_usd": config.min_volume_usd,
        "min_price_change_pct": config.min_price_change_pct,
        "max_coins": config.max_coins,
        "manual_watchlist": manual,
        "auto_tickers_top10": auto_preview,
        "final_list": final_list,
        "total_count": len(final_list),
    }

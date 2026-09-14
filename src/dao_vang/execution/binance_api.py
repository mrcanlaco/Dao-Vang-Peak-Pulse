import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from decimal import Decimal
from typing import Any
from urllib.parse import urlencode

from dao_vang.config.settings import ExecutionConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)


def format_to_step(value: float, step_size: str) -> str:
    """Format value to step size precision using Decimal truncation."""
    d_val = Decimal(str(value))
    d_step = Decimal(str(step_size))
    remainder = d_val % d_step
    d_val = d_val - remainder
    decimals = max(0, -d_step.as_tuple().exponent)
    return f"{d_val:.{decimals}f}"
class BinanceExecutionClient:
    """Authenticated client for Binance USD-M Futures execution."""

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.base_url = str(config.base_url).rstrip("/")
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.timeout_seconds = 10.0
        self._rules_cache: dict[str, dict[str, Any]] = {}
    def _sign(self, query_string: str) -> str:
        """Sign the query string with HMAC SHA256."""
        if not self.api_secret:
            raise ValueError("API secret is missing")
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _request(
        self,
        method: str,
        endpoint: str,
        params: dict[str, Any] | None = None,
        auth: bool = True,
    ) -> Any:
        """Send an HTTP request to Binance USD-M Futures."""
        params = params or {}
        if auth:
            if not self.api_key or not self.api_secret:
                logger.error("Missing API credentials for execution")
                raise ValueError("API credentials missing")
            params["timestamp"] = int(time.time() * 1000)
            query_dict = {k: v for k, v in params.items() if v is not None}
            query_string = urlencode(query_dict)
            signature = self._sign(query_string)
            query_string = f"{query_string}&signature={signature}"
        else:
            query_dict = {k: v for k, v in params.items() if v is not None}
            query_string = urlencode(query_dict)
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if method == "GET":
            url = f"{url}?{query_string}"
            data = None
        else:
            data = query_string.encode("utf-8")

        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("X-MBX-APIKEY", self.api_key)
        
        if self.config.paper_trading:
            logger.debug(f"[PAPER] {method} {url}")
            
        try:
            with urllib.request.urlopen(req, timeout=self.timeout_seconds) as response:
                body = response.read()
                return json.loads(body.decode("utf-8"))
        except urllib.error.HTTPError as e:
            error_body = e.read().decode("utf-8")
            logger.error(f"Binance API HTTP {e.code}: {error_body}")
            raise RuntimeError(f"Binance API error: {error_body}")
        except urllib.error.URLError as e:
            logger.error(f"Binance API connection error: {e}")
            raise RuntimeError(f"Binance connection error: {e}")

    def get_open_positions(self) -> list[dict[str, Any]]:
        """Fetch all open positions (positionAmt != 0)."""
        data = self._request("GET", "/fapi/v2/positionRisk")
        open_positions = [p for p in data if float(p.get("positionAmt", 0)) != 0]
        return open_positions

    def place_market_order(self, symbol: str, side: str, quantity: float, position_side: str = "BOTH") -> dict[str, Any]:
        """Place a market order."""
        params = {
            "symbol": symbol,
            "side": side,
            "positionSide": position_side,
            "type": "MARKET",
            "quantity": quantity,
        }
        return self._request("POST", "/fapi/v1/order", params)

    def get_symbol_rules(self, symbol: str) -> dict[str, Any]:
        """Fetch and cache trading rules (stepSize, tickSize, minQty, minNotional) for a symbol."""
        if symbol in self._rules_cache:
            return self._rules_cache[symbol]

        try:
            data = self._request("GET", "/fapi/v1/exchangeInfo", auth=False)
            for s in data.get("symbols", []):
                sym = s.get("symbol")
                step_size = "1"
                min_qty = 0.0
                tick_size = "0.01"
                min_notional = 5.0

                for f in s.get("filters", []):
                    ftype = f.get("filterType")
                    if ftype == "LOT_SIZE":
                        step_size = str(f.get("stepSize", "1"))
                        min_qty = float(f.get("minQty", 0.0))
                    elif ftype == "PRICE_FILTER":
                        tick_size = str(f.get("tickSize", "0.01"))
                    elif ftype == "MIN_NOTIONAL":
                        min_notional = float(f.get("notional", 5.0))

                self._rules_cache[sym] = {
                    "step_size": step_size,
                    "tick_size": tick_size,
                    "min_qty": min_qty,
                    "min_notional": min_notional,
                }
        except Exception as e:
            logger.error(f"Failed to fetch exchangeInfo: {e}")

        return self._rules_cache.get(
            symbol,
            {
                "step_size": "0.001",
                "tick_size": "0.01",
                "min_qty": 0.001,
                "min_notional": 5.0,
            },
        )

    def place_batch_orders(self, orders: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Place batch orders in a single HTTP request (up to 5 orders)."""
        params = {"batchOrders": json.dumps(orders)}
        res = self._request("POST", "/fapi/v1/batchOrders", params)
        if isinstance(res, dict) and "code" in res and res.get("code") != 200:
            raise RuntimeError(f"Batch order error: {res.get('msg')} (code {res.get('code')})")
        return res

    def place_bracket_short(
        self,
        symbol: str,
        quantity: float,
        entry_price: float,
        stop_loss_price: float,
        take_profit_price: float,
    ) -> dict[str, Any]:
        """Execute a SHORT entry with atomic/batch TP and SL orders."""
        rules = self.get_symbol_rules(symbol)
        qty_str = format_to_step(quantity, rules["step_size"])
        sl_str = format_to_step(stop_loss_price, rules["tick_size"])
        tp_str = format_to_step(take_profit_price, rules["tick_size"])

        notional = float(qty_str) * entry_price
        if notional < rules["min_notional"]:
            raise ValueError(
                f"Order notional ${notional:.2f} below minNotional ${rules['min_notional']:.2f}"
            )

        orders = [
            {
                "symbol": symbol,
                "side": "SELL",
                "type": "MARKET",
                "quantity": qty_str,
                "positionSide": "BOTH",
            },
            {
                "symbol": symbol,
                "side": "BUY",
                "type": "STOP_MARKET",
                "stopPrice": sl_str,
                "closePosition": "true",
                "positionSide": "BOTH",
            },
            {
                "symbol": symbol,
                "side": "BUY",
                "type": "TAKE_PROFIT_MARKET",
                "stopPrice": tp_str,
                "closePosition": "true",
                "positionSide": "BOTH",
            },
        ]

        try:
            results = self.place_batch_orders(orders)
            return {"batch": True, "results": results}
        except Exception as e:
            logger.warning(f"Batch orders failed ({e}). Falling back to sequential execution.")
            entry_res = self.place_market_order(symbol, "SELL", float(qty_str))
            sl_res = self._request(
                "POST",
                "/fapi/v1/order",
                {
                    "symbol": symbol,
                    "side": "BUY",
                    "type": "STOP_MARKET",
                    "stopPrice": sl_str,
                    "closePosition": "true",
                    "positionSide": "BOTH",
                },
            )
            tp_res = self._request(
                "POST",
                "/fapi/v1/order",
                {
                    "symbol": symbol,
                    "side": "BUY",
                    "type": "TAKE_PROFIT_MARKET",
                    "stopPrice": tp_str,
                    "closePosition": "true",
                    "positionSide": "BOTH",
                },
            )
            return {"batch": False, "results": [entry_res, sl_res, tp_res]}

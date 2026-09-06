import hashlib
import hmac
import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from dao_vang.config.settings import ExecutionConfig
from dao_vang.logging import get_logger

logger = get_logger(__name__)


class BinanceExecutionClient:
    """Authenticated client for Binance USD-M Futures execution."""

    def __init__(self, config: ExecutionConfig):
        self.config = config
        self.base_url = str(config.base_url).rstrip("/")
        self.api_key = config.api_key
        self.api_secret = config.api_secret
        self.timeout_seconds = 10.0

    def _sign(self, query_string: str) -> str:
        """Sign the query string with HMAC SHA256."""
        if not self.api_secret:
            raise ValueError("API secret is missing")
        return hmac.new(
            self.api_secret.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256,
        ).hexdigest()

    def _request(self, method: str, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Send an authenticated request to Binance."""
        if not self.api_key or not self.api_secret:
            logger.error("Missing API credentials for execution")
            raise ValueError("API credentials missing")

        params = params or {}
        # Binance requires a timestamp
        params["timestamp"] = int(time.time() * 1000)
        
        # Drop None
        query_dict = {k: v for k, v in params.items() if v is not None}
        query_string = urlencode(query_dict)
        signature = self._sign(query_string)
        query_string = f"{query_string}&signature={signature}"
        
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

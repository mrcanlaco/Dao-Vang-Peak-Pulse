import json
import time
import urllib.error
import urllib.request
from typing import Any
from urllib.parse import urlencode

from dao_vang.domain.errors import RateLimitError, SourceAPIError
from dao_vang.logging import get_logger

logger = get_logger(__name__)


class BinanceClient:
    """HTTP client for Binance USD-M Futures public API with retry and rate-limit handling."""

    def __init__(
        self,
        base_url: str = "https://fapi.binance.com",
        timeout_seconds: float = 15.0,
        max_retries: int = 5,
        respect_retry_after: bool = True,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.max_retries = max_retries
        self.respect_retry_after = respect_retry_after

    def get(self, endpoint: str, params: dict[str, Any] | None = None) -> Any:
        """Execute a GET request to the given endpoint."""
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        if params:
            # Drop None values
            query = {k: v for k, v in params.items() if v is not None}
            if query:
                url = f"{url}?{urlencode(query)}"

        retries = 0
        backoff = 1.0

        while True:
            req = urllib.request.Request(url, headers={"User-Agent": "dao_vang/0.1"})
            start_time = time.monotonic()

            try:
                with urllib.request.urlopen(
                    req, timeout=self.timeout_seconds
                ) as response:
                    duration = time.monotonic() - start_time
                    status = response.getcode()
                    headers = response.info()
                    used_weight = headers.get("X-MBX-USED-WEIGHT-1M", "unknown")

                    body = response.read()
                    data = json.loads(body)

                    logger.debug(
                        "binance_request_success",
                        endpoint=endpoint,
                        status=status,
                        duration_sec=round(duration, 3),
                        used_weight=used_weight,
                        retries=retries,
                    )
                    return data

            except urllib.error.HTTPError as e:
                duration = time.monotonic() - start_time
                status = e.code
                headers = e.headers

                logger.warning(
                    "binance_request_error",
                    endpoint=endpoint,
                    status=status,
                    duration_sec=round(duration, 3),
                    retries=retries,
                    error=str(e),
                )

                # Rate limit
                if status in (429, 418):
                    if retries >= self.max_retries:
                        raise RateLimitError(
                            f"Rate limit exceeded after {retries} retries: {status}"
                        )

                    retry_after = headers.get("Retry-After")
                    if (
                        self.respect_retry_after
                        and retry_after
                        and retry_after.isdigit()
                    ):
                        sleep_time = int(retry_after)
                    else:
                        sleep_time = backoff

                    logger.info(
                        "rate_limit_sleep", sleep_time=sleep_time, status=status
                    )
                    time.sleep(sleep_time)
                    retries += 1
                    backoff *= 2.0
                    continue

                # 5xx Server Error
                if 500 <= status < 600:
                    if retries >= self.max_retries:
                        raise SourceAPIError(
                            f"Server error after {retries} retries: {status}"
                        )

                    sleep_time = backoff
                    logger.info(
                        "server_error_sleep", sleep_time=sleep_time, status=status
                    )
                    time.sleep(sleep_time)
                    retries += 1
                    backoff *= 2.0
                    continue

                # 4xx Client Error (other than 429) - Do not retry
                try:
                    error_body = e.read().decode("utf-8")
                except Exception:
                    error_body = ""
                raise SourceAPIError(f"Client error {status}: {error_body}")

            except urllib.error.URLError as e:
                duration = time.monotonic() - start_time
                logger.warning(
                    "binance_network_error",
                    endpoint=endpoint,
                    duration_sec=round(duration, 3),
                    retries=retries,
                    error=str(e),
                )
                if retries >= self.max_retries:
                    raise SourceAPIError(f"Network error after {retries} retries: {e}")

                sleep_time = backoff
                time.sleep(sleep_time)
                retries += 1
                backoff *= 2.0
                continue

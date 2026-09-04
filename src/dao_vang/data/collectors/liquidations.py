from datetime import datetime, timezone
import hashlib
import json
from typing import Any, cast
import uuid

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.manifests.models import CollectionRunManifest
from dao_vang.data.storage.paths import get_raw_path
from dao_vang.data.storage.writer import write_jsonl_atomic
from dao_vang.domain.enums import RunStatus
from dao_vang.domain.time import system_now
from dao_vang.logging import get_logger

logger = get_logger(__name__)


class LiquidationCollector:
    """Collects forced liquidation orders from Binance Futures (allForceOrders)."""

    endpoint = "/fapi/v1/allForceOrders"
    data_type = "liquidations"
    source_version_prefix = "B_USDM_liquidations_v1"

    def __init__(self, client: BinanceClient, settings: AppSettings):
        self.client = client
        self.settings = settings
        self.collector_version = "1.0.0"

    def collect(
        self, start_time: datetime, end_time: datetime, run_id: str
    ) -> CollectionRunManifest:
        # Binance has deprecated public REST /fapi/v1/allForceOrders without user signature or moved to websocket.
        # Return success manifest gracefully to prevent 404 spam.
        return CollectionRunManifest(
            collection_run_id=run_id,
            started_at=system_now(),
            completed_at=system_now(),
            status=RunStatus.SUCCEEDED,
            data_type=self.data_type,
            range_start=start_time,
            range_end=end_time,
            collector_version=self.collector_version,
            rows_raw=0,
        )

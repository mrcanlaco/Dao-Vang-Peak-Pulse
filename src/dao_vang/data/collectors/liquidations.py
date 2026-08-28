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
        symbol = self.settings.binance.symbol

        run_manifest = CollectionRunManifest(
            collection_run_id=run_id,
            started_at=system_now(),
            status=RunStatus.RUNNING,
            data_type=self.data_type,
            range_start=start_time,
            range_end=end_time,
            collector_version=self.collector_version,
        )

        current_start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        limit = 100
        envelopes: list[dict[str, Any]] = []

        try:
            while current_start_ms <= end_ms:
                params = {
                    "symbol": symbol,
                    "startTime": current_start_ms,
                    "endTime": end_ms,
                    "limit": limit,
                }

                req_at = system_now()
                data = self.client.get(self.endpoint, params)
                rec_at = system_now()

                if not data or not isinstance(data, list):
                    break

                data_list = cast(list[dict[str, Any]], data)
                if not data_list:
                    break

                payload_json = json.dumps(data_list)
                response_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()
                src_ver = f"{self.source_version_prefix}_{self.collector_version}"

                envelope = {
                    "collection_run_id": run_id,
                    "request_id": str(uuid.uuid4()),
                    "provider": "Binance",
                    "product": "USD-M Futures",
                    "endpoint": self.endpoint,
                    "request_params_json": json.dumps(params),
                    "requested_at": req_at.isoformat(),
                    "received_at": rec_at.isoformat(),
                    "http_status": 200,
                    "response_hash_sha256": response_hash,
                    "source_version": src_ver,
                    "collector_version": self.collector_version,
                    "payload_json": payload_json,
                }

                envelopes.append(envelope)
                run_manifest.rows_raw += len(data_list)

                if len(data_list) < limit:
                    break

                last_item = data_list[-1]
                last_timestamp = int(last_item.get("time", 0))
                next_start = last_timestamp + 1
                if next_start <= current_start_ms:
                    break
                current_start_ms = next_start

            if envelopes:
                dt = start_time.date()
                raw_path_dir = get_raw_path(
                    self.settings.paths.data_dir, self.data_type, dt
                )
                target_file = raw_path_dir / f"{run_id}.jsonl"
                write_jsonl_atomic(target_file, envelopes)
                run_manifest.raw_file_paths.append(str(target_file))

            run_manifest.status = RunStatus.SUCCESS

        except Exception as e:
            logger.warning(
                "liquidation_collection_skipped",
                symbol=symbol,
                error=str(e),
            )
            run_manifest.status = RunStatus.FAILED
            run_manifest.error_count += 1
        finally:
            run_manifest.completed_at = system_now()

        return run_manifest

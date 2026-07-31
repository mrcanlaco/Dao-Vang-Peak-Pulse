import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.manifests.models import CollectionRunManifest
from dao_vang.data.storage.paths import get_raw_path
from dao_vang.data.storage.writer import write_jsonl_atomic
from dao_vang.domain.enums import RunStatus
from dao_vang.logging import get_logger

logger = get_logger(__name__)


class FundingCollector:
    def __init__(self, client: BinanceClient, settings: AppSettings):
        self.client = client
        self.settings = settings
        self.collector_version = "1.0.0"

    def collect(
        self, start_time: datetime, end_time: datetime, run_id: str
    ) -> CollectionRunManifest:
        """Collect funding rate data from Binance and store as JSONL."""
        symbol = self.settings.binance.symbol

        run_manifest = CollectionRunManifest(
            collection_run_id=run_id,
            started_at=datetime.now(timezone.utc),
            status=RunStatus.RUNNING,
            data_type="funding",
            range_start=start_time,
            range_end=end_time,
            collector_version=self.collector_version,
        )

        current_start_ms = int(start_time.timestamp() * 1000)
        end_ms = int(end_time.timestamp() * 1000)

        limit = 1000
        envelopes: list[dict[str, Any]] = []

        try:
            while current_start_ms <= end_ms:
                params = {
                    "symbol": symbol,
                    "startTime": current_start_ms,
                    "endTime": end_ms,
                    "limit": limit,
                }

                req_at = datetime.now(timezone.utc)
                data = self.client.get("/fapi/v1/fundingRate", params)
                rec_at = datetime.now(timezone.utc)

                if not data or not isinstance(data, list):
                    break

                data_list = cast(list[dict[str, Any]], data)

                payload_json = json.dumps(data_list)
                response_hash = hashlib.sha256(payload_json.encode("utf-8")).hexdigest()

                envelope = {
                    "collection_run_id": run_id,
                    "request_id": str(uuid.uuid4()),
                    "provider": "Binance",
                    "product": "USD-M Futures",
                    "endpoint": "/fapi/v1/fundingRate",
                    "request_params_json": json.dumps(params),
                    "requested_at": req_at.isoformat(),
                    "received_at": rec_at.isoformat(),
                    "http_status": 200,
                    "response_hash_sha256": response_hash,
                    "source_version": f"B_USDM_funding_v1_{self.collector_version}",
                    "collector_version": self.collector_version,
                    "payload_json": payload_json,
                }

                envelopes.append(envelope)
                run_manifest.rows_raw += len(data_list)

                last_item = data_list[-1]
                last_funding_time = int(last_item["fundingTime"])

                next_start = last_funding_time + 1
                if next_start <= current_start_ms:
                    logger.warning(
                        "Pagination did not advance",
                        current_start=current_start_ms,
                        next_start=next_start,
                    )
                    break

                current_start_ms = next_start

                if len(data_list) < limit:
                    break

            if envelopes:
                dt = start_time.date()
                raw_path_dir = get_raw_path(self.settings.paths.data_dir, "funding", dt)
                target_file = raw_path_dir / f"{run_id}.jsonl"

                write_jsonl_atomic(target_file, envelopes)

            run_manifest.status = RunStatus.SUCCEEDED

        except Exception as e:
            logger.error("funding_collection_failed", error=str(e))
            run_manifest.status = RunStatus.FAILED
            run_manifest.error_count += 1

        finally:
            run_manifest.completed_at = datetime.now(timezone.utc)

        return run_manifest

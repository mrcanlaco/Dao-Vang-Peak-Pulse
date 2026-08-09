import hashlib
import json
import uuid
from datetime import datetime, timezone
from typing import Any, cast

from dao_vang.config.settings import AppSettings
from dao_vang.data.collectors.binance_client import BinanceClient
from dao_vang.data.collectors.ratios import BaseRatioCollector

class TopPositionRatioCollector(BaseRatioCollector):
    endpoint = "/futures/data/topLongShortPositionRatio"
    data_type = "top_position_ratio"
    source_version_prefix = "B_USDM_top_position_ratio_v1"

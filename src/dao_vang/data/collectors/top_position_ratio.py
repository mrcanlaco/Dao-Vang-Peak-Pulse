
from dao_vang.data.collectors.ratios import BaseRatioCollector


class TopPositionRatioCollector(BaseRatioCollector):
    endpoint = "/futures/data/topLongShortPositionRatio"
    data_type = "top_position_ratio"
    source_version_prefix = "B_USDM_top_position_ratio_v1"

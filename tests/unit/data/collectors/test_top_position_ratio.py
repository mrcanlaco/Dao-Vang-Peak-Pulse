import pytest
from dao_vang.data.collectors.top_position_ratio import TopPositionRatioCollector

class MockClient: pass
class MockSettings: pass

def test_top_position_ratio_init():
    collector = TopPositionRatioCollector(client=MockClient(), settings=MockSettings())
    assert collector.data_type == "top_position_ratio"

# skipped: run test, add when fully hooked to pipeline

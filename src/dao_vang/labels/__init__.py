from dao_vang.labels.engine_v1 import DistributionLabelEngineV1
from dao_vang.labels.engine_v2 import DistributionLabelEngineV2
from dao_vang.labels.events import create_event_summary_table, group_events
from dao_vang.labels.models_v1 import DistributionLabelResultV1
from dao_vang.labels.specs.distribution_short_v1 import (
    DistributionShortV1Spec,
)
from dao_vang.labels.specs.distribution_short_v1 import (
    specs as v1_specs,
)
from dao_vang.labels.specs.distribution_short_v2 import (
    DistributionShortV2Spec,
)
from dao_vang.labels.specs.distribution_short_v2 import (
    specs as v2_specs,
)

# New training/materialization defaults use the 20%/24h v2 contract. Keep
# explicit v1 exports so historical bundles and audits remain reproducible.
specs = v2_specs

__all__ = [
    "DistributionShortV1Spec",
    "DistributionShortV2Spec",
    "specs",
    "v1_specs",
    "v2_specs",
    "DistributionLabelResultV1",
    "DistributionLabelEngineV1",
    "DistributionLabelEngineV2",
    "group_events",
    "create_event_summary_table",
]

import pytest

from dao_vang.features.models import FeatureDefinition, FeatureSetVersion
from dao_vang.features.registry import FeatureRegistry


def test_feature_registry_register_feature():
    registry = FeatureRegistry()
    feat = FeatureDefinition(
        id="price_ret_5m",
        version="0.1.0",
        description="5m price return",
    )
    registry.register_feature(feat)

    assert registry.get_feature("price_ret_5m") == feat

    # Register duplicate
    with pytest.raises(ValueError, match="already exists"):
        registry.register_feature(feat)


def test_feature_registry_register_feature_set():
    registry = FeatureRegistry()
    feat1 = FeatureDefinition(id="f1", version="1", description="f1")
    feat2 = FeatureDefinition(id="f2", version="1", description="f2")

    registry.register_feature(feat1)

    fset = FeatureSetVersion(
        id="mvp_v1", version="1.0", description="MVP features", features=[feat1, feat2]
    )

    # Should fail because feat2 is not registered
    with pytest.raises(ValueError, match="is not registered"):
        registry.register_feature_set(fset)

    registry.register_feature(feat2)
    registry.register_feature_set(fset)

    assert registry.get_feature_set("mvp_v1") == fset

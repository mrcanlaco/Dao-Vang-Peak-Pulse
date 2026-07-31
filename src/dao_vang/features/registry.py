from typing import Dict, List, Optional

from dao_vang.features.models import FeatureDefinition, FeatureSetVersion


class FeatureRegistry:
    """
    Registry for managing feature definitions and feature set versions.
    Ensures unique IDs and consistent versioning across the project.
    """

    def __init__(self):
        self._features: Dict[str, FeatureDefinition] = {}
        self._feature_sets: Dict[str, FeatureSetVersion] = {}

    def register_feature(self, feature: FeatureDefinition) -> None:
        if feature.id in self._features:
            raise ValueError(
                f"Feature with ID '{feature.id}' already exists in registry."
            )
        self._features[feature.id] = feature

    def get_feature(self, feature_id: str) -> Optional[FeatureDefinition]:
        return self._features.get(feature_id)

    def list_features(self) -> List[FeatureDefinition]:
        return list(self._features.values())

    def register_feature_set(self, feature_set: FeatureSetVersion) -> None:
        if feature_set.id in self._feature_sets:
            raise ValueError(
                f"Feature Set with ID '{feature_set.id}' already exists in registry."
            )

        # Validate that all features in the set are registered
        for feature in feature_set.features:
            if feature.id not in self._features:
                raise ValueError(
                    f"Feature '{feature.id}' in feature set '{feature_set.id}' "
                    "is not registered in the FeatureRegistry."
                )

        self._feature_sets[feature_set.id] = feature_set

    def get_feature_set(self, set_id: str) -> Optional[FeatureSetVersion]:
        return self._feature_sets.get(set_id)


# Global default instance
registry = FeatureRegistry()

class DaoVangError(Exception):
    """Base exception for all Đảo Vàng errors."""
    pass


class ConfigurationError(DaoVangError):
    """Raised when configuration is missing or invalid."""
    pass


class SourceAPIError(DaoVangError):
    """Raised when the source API returns an unexpected error."""
    pass


class RateLimitError(SourceAPIError):
    """Raised when the source API rate limit is exceeded."""
    pass


class SchemaError(DaoVangError):
    """Raised when data does not match the expected schema."""
    pass


class DataQualityError(DaoVangError):
    """Raised when data fails critical quality checks."""
    pass


class InsufficientDataError(DaoVangError):
    """Raised when there is not enough data to perform an operation."""
    pass


class PointInTimeViolation(DaoVangError):
    """Raised when a point-in-time invariant is violated."""
    pass


class LeakageDetected(DaoVangError):
    """Raised when future information leakage is detected."""
    pass


class ArtifactIntegrityError(DaoVangError):
    """Raised when artifact hashes or manifests do not match."""
    pass

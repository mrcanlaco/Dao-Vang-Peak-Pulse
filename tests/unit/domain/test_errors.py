from dao_vang.domain import (
    ArtifactIntegrityError,
    ConfigurationError,
    DaoVangError,
    DataQualityError,
    InsufficientDataError,
    LeakageDetected,
    PointInTimeViolation,
    RateLimitError,
    SchemaError,
    SourceAPIError,
)


def test_exception_inheritance() -> None:
    exceptions = [
        ConfigurationError,
        SourceAPIError,
        RateLimitError,
        SchemaError,
        DataQualityError,
        InsufficientDataError,
        PointInTimeViolation,
        LeakageDetected,
        ArtifactIntegrityError,
    ]
    
    for exc in exceptions:
        assert issubclass(exc, DaoVangError)

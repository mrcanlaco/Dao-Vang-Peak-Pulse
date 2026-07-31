# ERROR HANDLING

## Taxonomy

- ConfigurationError
- SourceAPIError
- RateLimitError
- SchemaError
- DataQualityError
- InsufficientDataError
- PointInTimeViolation
- LeakageDetected
- ArtifactIntegrityError

## Policy

- Retry chỉ lỗi retryable.
- Không nuốt lỗi.
- Error có context nhưng không chứa secret.
- Partial output không được coi thành công.
- Khi integrity hoặc point-in-time lỗi: fail closed.
- CLI map error thành exit code rõ.

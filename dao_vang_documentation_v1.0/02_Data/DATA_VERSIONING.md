# DATA VERSIONING

## Các version

- `source_version`
- `collector_version`
- `schema_version`
- `normalizer_version`
- `quality_rules_version`
- `alignment_version`
- `dataset_version`

## Dataset Version

Dataset version thay đổi khi:

- input source snapshot đổi;
- parser semantic đổi;
- quality exclusion đổi;
- availability lag đổi;
- alignment rule đổi;
- schema semantic đổi.

## Fingerprint

Hash canonical của:

- source file hashes;
- config;
- schema;
- rules versions;
- min/max time;
- row count.

Cùng fingerprint phải tạo cùng output.

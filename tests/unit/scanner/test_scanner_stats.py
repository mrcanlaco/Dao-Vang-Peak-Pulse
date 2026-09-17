import json
from types import SimpleNamespace

import duckdb

from dao_vang.scanner.daemon import ScannerDaemon


def test_stats_do_not_execute_views_or_expose_working_tables(tmp_path):
    with duckdb.connect() as conn:
        touched = []

        def expensive(value: int) -> int:
            touched.append(value)
            raise AssertionError("Telemetry must not re-run the price lake")

        conn.create_function("expensive", expensive)
        conn.execute("CREATE TABLE feature_results AS SELECT TIMESTAMP '2026-09-18 00:00:00' AS feature_time")
        conn.execute("CREATE VIEW v3_runtime_prices AS SELECT expensive(1) AS close_time")
        conn.execute("CREATE TEMP TABLE temporary_source AS SELECT 1 AS value")
        conn.execute("CREATE TABLE bf_features AS SELECT 1 AS value")
        daemon = ScannerDaemon.__new__(ScannerDaemon)
        daemon._system_stats_path = tmp_path / "stats.json"
        daemon._publish_system_stats(SimpleNamespace(conn=conn))
        result = json.loads(daemon._system_stats_path.read_text())
    assert touched == []
    assert result["data_stats_scope"] == "persistent_tables"
    assert [row["table"] for row in result["data_stats"]] == ["feature_results"]
    assert result["data_stats"][0]["rows"] == 1
    assert result["data_stats"][0]["max_time"].startswith("2026-09-18T07:00:00")

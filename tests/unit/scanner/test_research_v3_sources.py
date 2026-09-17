from datetime import datetime, timedelta, timezone

import pyarrow as pa
import pyarrow.parquet as pq

from dao_vang.scanner.research_v3_sources import SourceCatalog, _backfill_metadata

NOW = datetime(2026, 9, 18, tzinfo=timezone.utc)


def write(path, symbols, collected=NOW):
    path.parent.mkdir(parents=True, exist_ok=True)
    pq.write_table(pa.table({"symbol": symbols, "collected_at": [collected] * len(symbols)}), path)


def test_hashed_backfills_are_routed_by_footer_once_per_file_version(tmp_path, monkeypatch):
    from dao_vang.scanner import research_v3_sources as sources

    path = tmp_path / "normalized/klines/date=2026-09-01/v3bf_oldhash.parquet"
    write(path, ["AAAUSDT"])
    _backfill_metadata.cache_clear()
    read = pq.read_metadata
    reads = []

    def counted(name):
        reads.append(name)
        return read(name)

    monkeypatch.setattr(sources.pq, "read_metadata", counted)
    for _ in range(3):
        catalog = SourceCatalog(tmp_path)
        assert catalog.paths("klines", "AAAUSDT", NOW.timestamp()-60) == [path.as_posix()]
        assert catalog.paths("klines", "OTHERUSDT", NOW.timestamp()-60) == []
    assert len(reads) == 1
    # Atomic replacement/change must invalidate metadata, including after restart.
    write(path, ["OTHERUSDT", "OTHERUSDT"])
    catalog = SourceCatalog(tmp_path)
    assert catalog.paths("klines", "AAAUSDT", 0) == []
    assert catalog.paths("klines", "OTHERUSDT", 0) == [path.as_posix()]
    assert len(reads) == 2


def test_old_receipts_pruned_but_unknown_mixed_and_corrupt_remain_eligible(tmp_path):
    root = tmp_path / "normalized/funding/date=2026-01-01"
    write(root / "v3bf_old.parquet", ["AAAUSDT"], NOW-timedelta(days=60))
    write(root / "v3bf_mixed.parquet", ["AAAUSDT", "OTHERUSDT"])
    (root / "v3bf_bad.parquet").write_text("invalid")
    (root / "import_unknown.parquet").write_text("unknown")
    catalog = SourceCatalog(tmp_path)
    assert {sources.rsplit("/", 1)[-1] for sources in catalog.paths("funding", "AAAUSDT", NOW.timestamp()-60)} == {
        "v3bf_mixed.parquet", "v3bf_bad.parquet", "import_unknown.parquet"}


def test_inventory_is_shared_across_coins_and_new_downloads(tmp_path, monkeypatch):
    from pathlib import Path

    root = tmp_path / "normalized/klines/date=2026-09-18"
    root.mkdir(parents=True)
    (root / f"scan_{int(NOW.timestamp())}_1_AAAUSDT.parquet").touch()
    calls = []
    original = Path.rglob

    def counted(self, pattern):
        calls.append(self)
        return original(self, pattern)

    monkeypatch.setattr(Path, "rglob", counted)
    catalog = SourceCatalog(tmp_path)
    assert len(catalog.paths("klines", "AAAUSDT", 0)) == 1
    assert catalog.paths("klines", "BBBUSDT", 0) == []
    new = root / "v3bf_download.parquet"
    write(new, ["BBBUSDT"])
    catalog.add("klines", "BBBUSDT", new)
    assert catalog.paths("klines", "BBBUSDT", 0) == [new.as_posix()]
    assert len(calls) == 1

from pathlib import Path
from dao_vang.data.storage.writer import compute_checksum, write_atomic, write_jsonl_atomic

def test_write_atomic(tmp_path: Path) -> None:
    target = tmp_path / "test.txt"
    data = b"hello world"
    checksum = write_atomic(target, data)
    
    assert target.exists()
    assert target.read_bytes() == data
    assert checksum == "b94d27b9934d3e08a52e52d7da7dabfac484efe37a5380ee9088f7ace2efcde9"

def test_write_jsonl_atomic(tmp_path: Path) -> None:
    target = tmp_path / "test.jsonl"
    items = [{"a": 1}, {"b": 2}]
    checksum = write_jsonl_atomic(target, items)
    
    assert target.exists()
    content = target.read_text("utf-8")
    assert content == '{"a":1}\n{"b":2}\n'
    assert checksum == compute_checksum(target)

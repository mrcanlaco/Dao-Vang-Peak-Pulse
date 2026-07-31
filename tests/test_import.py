"""Smoke tests for Đảo Vàng package."""

import dao_vang


def test_package_importable() -> None:
    """Verify that the core package can be imported and has the correct version."""
    assert dao_vang.__version__ == "0.1.0"

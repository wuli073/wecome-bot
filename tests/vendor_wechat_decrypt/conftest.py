from __future__ import annotations

import sys
from pathlib import Path

import pytest


@pytest.fixture(autouse=True)
def vendor_module_path():
    vendor_path = Path(__file__).resolve().parents[2] / 'vendor' / 'wechat_decrypt'
    original_path = list(sys.path)
    sys.path.insert(0, str(vendor_path))
    try:
        yield
    finally:
        sys.path[:] = original_path

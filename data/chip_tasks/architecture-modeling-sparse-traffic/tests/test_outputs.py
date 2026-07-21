import math, pytest
from model import sparse_storage

def test_rounding():
    assert sparse_storage(10, .21, 2, 5) == {
        "nonzeros": 3, "data_bytes": 6, "metadata_bytes": 2,
        "total_bytes": 8, "compression_ratio": 2.5}

def test_empty():
    assert math.isinf(sparse_storage(10, 0, 4, 8)["compression_ratio"])

def test_invalid():
    with pytest.raises(ValueError): sparse_storage(4, 1.1, 2, 1)

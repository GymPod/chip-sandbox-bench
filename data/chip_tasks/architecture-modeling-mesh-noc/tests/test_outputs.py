import pytest
from model import mesh_latency

def test_routes():
    assert mesh_latency(0, 0, 4, 3, 2, 1) == 2
    assert mesh_latency(0, 11, 4, 3, 2, 1) == 17
    assert mesh_latency(5, 6, 4, 3, 2, 3) == 7

def test_invalid():
    with pytest.raises(ValueError): mesh_latency(0, 12, 4, 3, 1, 1)

import math, pytest
from model import roofline

def test_memory_and_compute_bound():
    assert roofline(100, 100, 20, 4)["cycles"] == 25
    assert roofline(100, 10, 20, 4)["cycles"] == 5

def test_zero_bytes_and_work():
    result = roofline(10, 0, 5, 2)
    assert math.isinf(result["arithmetic_intensity"]) and result["cycles"] == 2
    assert roofline(0, 0, 5, 2)["cycles"] == 0

def test_invalid():
    with pytest.raises(ValueError): roofline(1, 1, 0, 1)

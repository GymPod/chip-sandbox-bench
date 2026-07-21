import pytest
from model import simulate_fifo

def test_trace_and_accounting():
    assert simulate_fifo(3, [(2, 1), (3, 1), (0, 4)]) == {
        "occupancy": [2, 3, 0], "accepted": 4, "dropped": 1, "underflow": 2}

def test_same_cycle_read_does_not_see_write():
    assert simulate_fifo(1, [(1, 1)])["underflow"] == 1

def test_invalid():
    with pytest.raises(ValueError): simulate_fifo(-1, [])

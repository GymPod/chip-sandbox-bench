import pytest
from model import average_memory_access_time

def test_two_levels():
    levels = [{"hit_latency": 1, "local_hit_rate": .9}, {"hit_latency": 8, "local_hit_rate": .75}]
    assert average_memory_access_time(levels, 80) == pytest.approx(3.8)

def test_empty_and_complete_hits():
    assert average_memory_access_time([], 23) == 23
    assert average_memory_access_time([{"hit_latency": 2, "local_hit_rate": 1}], 100) == 2

def test_validation():
    with pytest.raises(ValueError):
        average_memory_access_time([{"hit_latency": 1, "local_hit_rate": 1.1}], 4)
    with pytest.raises(ValueError):
        average_memory_access_time([], -1)

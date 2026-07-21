import pytest
from model import pipeline_cycles

def test_latency_and_width():
    assert pipeline_cycles(1, 5, 1, []) == 5
    assert pipeline_cycles(10, 5, 2, []) == 9
    assert pipeline_cycles(10, 5, 2, [2, 3]) == 14
    assert pipeline_cycles(0, 5, 2, [4]) == 0

@pytest.mark.parametrize("args", [(-1, 5, 1, []), (1, 0, 1, []), (1, 5, 0, []), (1, 5, 1, [-1])])
def test_invalid(args):
    with pytest.raises(ValueError): pipeline_cycles(*args)

import pytest
from model import mm1_metrics

def test_metrics_and_little_law():
    m = mm1_metrics(2, 5)
    assert m["utilization"] == .4
    assert m["system_time"] == pytest.approx(1/3)
    assert m["waiting_time"] == pytest.approx(2/15)
    assert m["jobs_system"] == pytest.approx(2/3)
    assert m["jobs_waiting"] == pytest.approx(4/15)

def test_zero_arrivals():
    assert mm1_metrics(0, 4)["jobs_system"] == 0

def test_unstable():
    with pytest.raises(ValueError): mm1_metrics(5, 5)

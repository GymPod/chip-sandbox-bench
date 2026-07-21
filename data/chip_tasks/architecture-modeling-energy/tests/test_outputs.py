import pytest
from model import aggregate_energy

def test_aggregation():
    counts = {"mac": {"compute": 10}, "sram": {"read": 4, "write": 2}}
    table = {"mac": {"compute": 3}, "sram": {"read": .5, "write": 1}, "dram": {"read": 99}}
    assert aggregate_energy(counts, table) == {"components": {"mac": 30.0, "sram": 4.0}, "total": 34.0}

def test_missing_and_negative():
    with pytest.raises(KeyError): aggregate_energy({"x": {"read": 1}}, {})
    with pytest.raises(ValueError): aggregate_energy({"x": {"read": -1}}, {"x": {"read": 2}})

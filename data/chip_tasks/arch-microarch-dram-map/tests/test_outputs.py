import pytest
from model import map_dram

def test_field_progression():
    g = (64, 2, 4, 1024)
    assert map_dram(0, *g) == {"offset": 0, "channel": 0, "bank": 0, "column": 0, "row": 0}
    assert map_dram(64, *g)["channel"] == 1
    assert map_dram(128, *g)["bank"] == 1
    assert map_dram(512, *g)["column"] == 1
    assert map_dram(8192, *g)["row"] == 1

def test_offset():
    assert map_dram(67, 64, 1, 1, 256)["offset"] == 3

def test_invalid():
    with pytest.raises(ValueError): map_dram(0, 48, 2, 4, 1024)

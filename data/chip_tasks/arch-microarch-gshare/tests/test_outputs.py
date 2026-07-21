import pytest
from model import GShare

def test_saturation_and_prediction():
    p = GShare(8, 0)
    assert p.predict(0)
    p.update(0, False)
    assert not p.predict(0)
    for _ in range(5): p.update(0, False)
    assert p.table[0] == 0
    for _ in range(5): p.update(0, True)
    assert p.table[0] == 3

def test_history_changes_index_after_update():
    p = GShare(8, 3)
    p.update(0x40, True)
    assert p.history == 1
    assert p._index(0x40) == 1

def test_invalid():
    with pytest.raises(ValueError): GShare(3, 2)
    with pytest.raises(ValueError): GShare(4, -1)

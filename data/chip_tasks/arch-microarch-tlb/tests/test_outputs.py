import pytest
from model import FullyAssociativeTLB

def test_translation_and_offset():
    t = FullyAssociativeTLB(2, 4096); t.insert(2, 9)
    assert t.lookup(2 * 4096 + 17) == 9 * 4096 + 17
    assert t.lookup(3 * 4096) is None

def test_lru_refresh_and_invalidate():
    t = FullyAssociativeTLB(2, 16)
    t.insert(1, 11); t.insert(2, 12); t.lookup(16); t.insert(3, 13)
    assert t.lookup(32) is None and t.lookup(16) == 176
    t.invalidate(1); assert t.lookup(16) is None

def test_invalid():
    with pytest.raises(ValueError): FullyAssociativeTLB(0, 4096)

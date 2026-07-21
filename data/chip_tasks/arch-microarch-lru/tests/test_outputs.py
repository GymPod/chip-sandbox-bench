import pytest
from model import LRUSet

def test_fill_and_recency():
    s = LRUSet(3)
    assert s.victim() == 0
    s.touch(0); assert s.victim() == 1
    s.touch(1); s.touch(2); assert s.victim() == 0
    s.touch(0); assert s.victim() == 1

def test_invalidate():
    s = LRUSet(2)
    s.touch(0); s.touch(1); s.invalidate(1)
    assert s.victim() == 1

def test_errors():
    with pytest.raises(ValueError): LRUSet(0)
    with pytest.raises(IndexError): LRUSet(2).touch(2)

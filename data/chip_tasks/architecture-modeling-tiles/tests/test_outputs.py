import pytest
from model import enumerate_tiles

def test_divisibility_and_capacity():
    assert enumerate_tiles((4, 6), 8) == [
        (1, 1), (1, 2), (1, 3), (1, 6), (2, 1), (2, 2), (2, 3), (4, 1), (4, 2)]

def test_exact_capacity():
    assert (4, 4) in enumerate_tiles((8, 8), 16)
    assert (8, 4) not in enumerate_tiles((8, 8), 16)

def test_invalid():
    with pytest.raises(ValueError): enumerate_tiles((), 4)

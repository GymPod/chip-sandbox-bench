import pytest
from model import decode_address

def test_known_addresses():
    assert decode_address(0x1234, 64, 256) == (0, 0x48, 0x34)
    assert decode_address(0x5234, 64, 256) == (1, 0x48, 0x34)

def test_boundaries():
    assert decode_address(63, 64, 4) == (0, 0, 63)
    assert decode_address(64, 64, 4) == (0, 1, 0)
    assert decode_address(256, 64, 4) == (1, 0, 0)

@pytest.mark.parametrize("args", [(-1, 64, 4), (0, 0, 4), (0, 48, 4), (0, 64, 3)])
def test_invalid(args):
    with pytest.raises(ValueError):
        decode_address(*args)

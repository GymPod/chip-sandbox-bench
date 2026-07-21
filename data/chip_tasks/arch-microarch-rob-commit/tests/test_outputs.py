import copy, pytest
from model import commit_ready

def test_head_block_and_width():
    assert commit_ready([{"ready": False}, {"ready": True}], 4) == []
    assert commit_ready([{"ready": True}] * 4, 2) == [0, 1]

def test_exception_stops_commit():
    entries = [{"ready": True}, {"ready": True, "exception": True}, {"ready": True}]
    before = copy.deepcopy(entries)
    assert commit_ready(entries, 4) == [0, 1]
    assert entries == before

def test_invalid():
    with pytest.raises(ValueError): commit_ready([], -1)

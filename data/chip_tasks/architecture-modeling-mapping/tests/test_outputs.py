from model import validate_mapping

def test_valid():
    assert validate_mapping({"M": 16, "N": 12}, {"M": 4, "N": 3}) == []

def test_all_error_classes_sorted():
    assert validate_mapping({"M": 16, "N": 10, "P": 4}, {"M": 3, "N": 0, "Z": 2}) == [
        "M: factor does not divide extent", "N: values must be positive",
        "P: missing factor", "Z: unknown dimension"]

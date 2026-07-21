import copy
import importlib.util
from pathlib import Path


def load_module():
    spec = importlib.util.spec_from_file_location("dse", Path("/workspace/dse.py"))
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    spec.loader.exec_module(module)
    return module


def test_empty_space():
    assert load_module().pareto_frontier([]) == []


def test_clear_winner_dominates_other_designs():
    designs = [
        {"id": "slow", "latency": 12, "energy": 9, "area": 8},
        {"id": "winner", "latency": 8, "energy": 7, "area": 6},
        {"id": "large", "latency": 9, "energy": 8, "area": 12},
    ]
    assert load_module().pareto_frontier(designs) == ["winner"]


def test_tradeoffs_remain_on_frontier():
    designs = [
        {"id": "balanced", "latency": 8, "energy": 8, "area": 8},
        {"id": "fast", "latency": 4, "energy": 14, "area": 10},
        {"id": "efficient", "latency": 12, "energy": 3, "area": 9},
        {"id": "small", "latency": 11, "energy": 12, "area": 2},
        {"id": "dominated", "latency": 13, "energy": 13, "area": 9},
    ]
    assert load_module().pareto_frontier(designs) == [
        "balanced",
        "efficient",
        "fast",
        "small",
    ]


def test_equal_metric_points_do_not_dominate_each_other():
    designs = [
        {"id": "b", "latency": 5, "energy": 6, "area": 7},
        {"id": "a", "latency": 5, "energy": 6, "area": 7},
    ]
    assert load_module().pareto_frontier(designs) == ["a", "b"]


def test_input_is_not_mutated():
    designs = [
        {"id": "x", "latency": 1.5, "energy": 7.0, "area": 3.0},
        {"id": "y", "latency": 2.0, "energy": 6.0, "area": 3.0},
    ]
    original = copy.deepcopy(designs)
    load_module().pareto_frontier(designs)
    assert designs == original

#!/usr/bin/env python3
"""Materialize the additional chip benchmark tasks from compact definitions."""

from __future__ import annotations

import argparse
import json
import shutil
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
TASK_ROOT = ROOT / "data" / "chip_tasks"

COMMITS = {
    "archgym": "53f745af87b256794c0cd712c2b8e77aab74b4a6",
    "champsim": "51588e1d6f97875fe8de1a3621d28668bff83fcf",
    "gem5": "51edbbb9cfd37e92e9901aea2caa4a8f20eda005",
    "systemc": "adb09b1e3f998db9cce702fb8dce22a302c58001",
    "timeloop": "2d5510807128e9bd5f1cad0705cdf2ec4612fd4e",
    "verilog-eval": "c498220d0a52248f8e3fdffe279075215bde2da6",
    "opentitan": "b583fba84cfd9603694abab6a1f8e97cf2cfcd19",
    "zephyr": "3df5fa4d3fcf664373ffa64b88975ffe2f3a6b68",
}


def write(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content.rstrip() + "\n", encoding="utf-8")


def task_dir(task_id: str) -> Path:
    path = TASK_ROOT / task_id
    if path.exists():
        shutil.rmtree(path)
    return path


def metadata(
    task_id: str,
    discipline: str,
    benchmark: str,
    tools: list[str],
    repo: str,
    paths: list[str],
    prompt: str,
) -> dict[str, object]:
    repo_dir = "timeloop-accelergy-exercises" if repo == "timeloop" else repo
    return {
        "task_id": task_id,
        "discipline": discipline,
        "benchmark": benchmark,
        "tools": tools,
        "source": {
            "repo": f"benchmarks/{repo_dir}",
            "commit": COMMITS[repo],
            "paths": paths,
        },
        "prompt": prompt,
        "instruction": prompt,
    }


def python_task(spec: dict[str, object]) -> None:
    path = task_dir(str(spec["task_id"]))
    write(path / "task.json", json.dumps(spec["meta"], indent=2))
    write(path / "workspace" / "model.py", str(spec["starter"]))
    write(path / "tests" / "test_outputs.py", str(spec["tests"]))
    write(
        path / "solution" / "solve.sh",
        "#!/bin/sh\nset -eu\ncat > /workspace/model.py <<'PY'\n"
        + str(spec["solution"]).rstrip()
        + "\nPY",
    )


ARCH_TASKS = [
    {
        "task_id": "arch-microarch-cache-address",
        "meta": metadata(
            "arch-microarch-cache-address",
            "Architecture & Microarchitecture",
            "gem5",
            ["python3", "pytest"],
            "gem5",
            ["src/mem/cache/tags/base.hh", "src/mem/cache/cache.cc"],
            "Implement decode_address(address, line_bytes, sets) in model.py. "
            "Return (tag, set_index, block_offset) for a physically indexed cache. "
            "line_bytes and sets must be positive powers of two; reject invalid inputs "
            "with ValueError. Addresses are non-negative integers.",
        ),
        "starter": """def decode_address(address: int, line_bytes: int, sets: int) -> tuple[int, int, int]:
    raise NotImplementedError
""",
        "solution": """def decode_address(address: int, line_bytes: int, sets: int) -> tuple[int, int, int]:
    if address < 0 or line_bytes <= 0 or sets <= 0:
        raise ValueError("invalid cache geometry or address")
    if line_bytes & (line_bytes - 1) or sets & (sets - 1):
        raise ValueError("cache geometry must use powers of two")
    offset = address & (line_bytes - 1)
    block = address // line_bytes
    return block // sets, block & (sets - 1), offset
""",
        "tests": """import pytest
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
""",
    },
    {
        "task_id": "arch-microarch-amat",
        "meta": metadata(
            "arch-microarch-amat",
            "Architecture & Microarchitecture",
            "ArchGym",
            ["python3", "pytest"],
            "archgym",
            ["settings/default_sniper.yaml", "settings/default_timeloop.yaml"],
            "Implement average_memory_access_time(levels, memory_latency) in model.py. "
            "Each cache level is a dict with hit_latency and local_hit_rate, where the "
            "rate is conditional on reaching that level. Return the expected latency, "
            "including lookup latency at every reached cache and memory latency on a "
            "complete miss. Validate non-negative latencies and rates in [0, 1].",
        ),
        "starter": """def average_memory_access_time(levels: list[dict], memory_latency: float) -> float:
    raise NotImplementedError
""",
        "solution": """def average_memory_access_time(levels: list[dict], memory_latency: float) -> float:
    if memory_latency < 0:
        raise ValueError("negative latency")
    expected = 0.0
    reach = 1.0
    for level in levels:
        latency = float(level["hit_latency"])
        rate = float(level["local_hit_rate"])
        if latency < 0 or not 0.0 <= rate <= 1.0:
            raise ValueError("invalid cache level")
        expected += reach * latency
        reach *= 1.0 - rate
    return expected + reach * memory_latency
""",
        "tests": """import pytest
from model import average_memory_access_time

def test_two_levels():
    levels = [{"hit_latency": 1, "local_hit_rate": .9}, {"hit_latency": 8, "local_hit_rate": .75}]
    assert average_memory_access_time(levels, 80) == pytest.approx(3.8)

def test_empty_and_complete_hits():
    assert average_memory_access_time([], 23) == 23
    assert average_memory_access_time([{"hit_latency": 2, "local_hit_rate": 1}], 100) == 2

def test_validation():
    with pytest.raises(ValueError):
        average_memory_access_time([{"hit_latency": 1, "local_hit_rate": 1.1}], 4)
    with pytest.raises(ValueError):
        average_memory_access_time([], -1)
""",
    },
    {
        "task_id": "arch-microarch-gshare",
        "meta": metadata(
            "arch-microarch-gshare",
            "Architecture & Microarchitecture",
            "ChampSim",
            ["python3", "pytest"],
            "champsim",
            ["branch/gshare/gshare.cc", "branch/gshare/gshare.h"],
            "Implement GShare in model.py. The predictor has a power-of-two table of "
            "2-bit saturating counters initialized weakly taken (2), an N-bit global "
            "history register, and indexes with (pc >> 2) XOR history. predict returns "
            "taken for counters >= 2. update changes the indexed counter and then shifts "
            "the actual outcome into history. Reject invalid table/history sizes.",
        ),
        "starter": """class GShare:
    def __init__(self, entries: int, history_bits: int):
        raise NotImplementedError

    def predict(self, pc: int) -> bool:
        raise NotImplementedError

    def update(self, pc: int, taken: bool) -> None:
        raise NotImplementedError
""",
        "solution": """class GShare:
    def __init__(self, entries: int, history_bits: int):
        if entries <= 0 or entries & (entries - 1) or history_bits < 0:
            raise ValueError("invalid predictor geometry")
        self.table = [2] * entries
        self.mask = entries - 1
        self.history_mask = (1 << history_bits) - 1
        self.history = 0

    def _index(self, pc: int) -> int:
        return ((pc >> 2) ^ self.history) & self.mask

    def predict(self, pc: int) -> bool:
        return self.table[self._index(pc)] >= 2

    def update(self, pc: int, taken: bool) -> None:
        index = self._index(pc)
        self.table[index] = min(3, self.table[index] + 1) if taken else max(0, self.table[index] - 1)
        self.history = ((self.history << 1) | int(taken)) & self.history_mask
""",
        "tests": """import pytest
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
""",
    },
    {
        "task_id": "arch-microarch-lru",
        "meta": metadata(
            "arch-microarch-lru",
            "Architecture & Microarchitecture",
            "ChampSim",
            ["python3", "pytest"],
            "champsim",
            ["replacement/lru/lru.cc", "inc/util/lru_table.h"],
            "Implement LRUSet in model.py for one cache set. Lines are numbered from "
            "0 through ways-1. touch marks a line most recently used. victim must return "
            "the least recently touched line, preferring never-touched lines in ascending "
            "line order. invalidate makes a line eligible as never touched. Reject invalid "
            "line numbers and non-positive associativity.",
        ),
        "starter": """class LRUSet:
    def __init__(self, ways: int):
        raise NotImplementedError
    def touch(self, line: int) -> None:
        raise NotImplementedError
    def invalidate(self, line: int) -> None:
        raise NotImplementedError
    def victim(self) -> int:
        raise NotImplementedError
""",
        "solution": """class LRUSet:
    def __init__(self, ways: int):
        if ways <= 0:
            raise ValueError("ways must be positive")
        self.ways = ways
        self.order = []
    def _check(self, line: int) -> None:
        if not 0 <= line < self.ways:
            raise IndexError(line)
    def touch(self, line: int) -> None:
        self._check(line)
        if line in self.order:
            self.order.remove(line)
        self.order.append(line)
    def invalidate(self, line: int) -> None:
        self._check(line)
        if line in self.order:
            self.order.remove(line)
    def victim(self) -> int:
        for line in range(self.ways):
            if line not in self.order:
                return line
        return self.order[0]
""",
        "tests": """import pytest
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
""",
    },
    {
        "task_id": "arch-microarch-rob-commit",
        "meta": metadata(
            "arch-microarch-rob-commit",
            "Architecture & Microarchitecture",
            "gem5",
            ["python3", "pytest"],
            "gem5",
            ["src/cpu/o3/rob.hh", "src/cpu/o3/rob.cc"],
            "Implement commit_ready(entries, width) in model.py. Entries are in program "
            "order and contain ready and exception booleans. Return the indices committed "
            "this cycle. Commit at most width contiguous ready entries from the head. An "
            "unready head blocks younger entries. An exception entry may commit but ends "
            "the cycle immediately. Reject negative width and do not mutate entries.",
        ),
        "starter": """def commit_ready(entries: list[dict], width: int) -> list[int]:
    raise NotImplementedError
""",
        "solution": """def commit_ready(entries: list[dict], width: int) -> list[int]:
    if width < 0:
        raise ValueError("negative width")
    committed = []
    for index, entry in enumerate(entries[:width]):
        if not entry["ready"]:
            break
        committed.append(index)
        if entry.get("exception", False):
            break
    return committed
""",
        "tests": """import copy, pytest
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
""",
    },
    {
        "task_id": "arch-microarch-dram-map",
        "meta": metadata(
            "arch-microarch-dram-map",
            "Architecture & Microarchitecture",
            "gem5",
            ["python3", "pytest"],
            "gem5",
            ["src/mem/mem_ctrl.hh", "src/mem/DRAMInterface.py"],
            "Implement map_dram(address, burst_bytes, channels, banks, row_bytes). "
            "Decode low-order fields in this order: burst offset, channel, bank, column "
            "within a row, then row. All geometry values must be positive powers of two "
            "and row_bytes must be divisible by burst_bytes. Return a dict containing "
            "offset, channel, bank, column, and row.",
        ),
        "starter": """def map_dram(address: int, burst_bytes: int, channels: int, banks: int, row_bytes: int) -> dict:
    raise NotImplementedError
""",
        "solution": """def map_dram(address: int, burst_bytes: int, channels: int, banks: int, row_bytes: int) -> dict:
    values = (burst_bytes, channels, banks, row_bytes)
    if address < 0 or any(v <= 0 or v & (v - 1) for v in values) or row_bytes % burst_bytes:
        raise ValueError("invalid DRAM geometry")
    offset = address % burst_bytes
    value = address // burst_bytes
    channel = value % channels; value //= channels
    bank = value % banks; value //= banks
    columns = row_bytes // burst_bytes
    column = value % columns
    row = value // columns
    return {"offset": offset, "channel": channel, "bank": bank, "column": column, "row": row}
""",
        "tests": """import pytest
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
""",
    },
    {
        "task_id": "arch-microarch-tlb",
        "meta": metadata(
            "arch-microarch-tlb",
            "Architecture & Microarchitecture",
            "gem5",
            ["python3", "pytest"],
            "gem5",
            ["src/arch/generic/tlb.hh", "src/arch/x86/tlb.hh"],
            "Implement FullyAssociativeTLB in model.py with LRU replacement. lookup(va) "
            "returns the translated physical address or None and refreshes recency on a "
            "hit. insert(vpn, ppn) updates an existing mapping or evicts the LRU mapping "
            "when full. invalidate removes a VPN. Preserve page offsets and support only "
            "positive entry counts and power-of-two page sizes.",
        ),
        "starter": """class FullyAssociativeTLB:
    def __init__(self, entries: int, page_size: int):
        raise NotImplementedError
    def lookup(self, virtual_address: int):
        raise NotImplementedError
    def insert(self, vpn: int, ppn: int) -> None:
        raise NotImplementedError
    def invalidate(self, vpn: int) -> None:
        raise NotImplementedError
""",
        "solution": """class FullyAssociativeTLB:
    def __init__(self, entries: int, page_size: int):
        if entries <= 0 or page_size <= 0 or page_size & (page_size - 1):
            raise ValueError("invalid TLB geometry")
        self.entries = entries
        self.page_size = page_size
        self.map = {}
        self.order = []
    def _touch(self, vpn):
        if vpn in self.order: self.order.remove(vpn)
        self.order.append(vpn)
    def lookup(self, virtual_address: int):
        vpn, offset = divmod(virtual_address, self.page_size)
        if vpn not in self.map: return None
        self._touch(vpn)
        return self.map[vpn] * self.page_size + offset
    def insert(self, vpn: int, ppn: int) -> None:
        if vpn not in self.map and len(self.map) == self.entries:
            del self.map[self.order.pop(0)]
        self.map[vpn] = ppn
        self._touch(vpn)
    def invalidate(self, vpn: int) -> None:
        self.map.pop(vpn, None)
        if vpn in self.order: self.order.remove(vpn)
""",
        "tests": """import pytest
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
""",
    },
    {
        "task_id": "arch-microarch-pipeline",
        "meta": metadata(
            "arch-microarch-pipeline",
            "Architecture & Microarchitecture",
            "gem5",
            ["python3", "pytest"],
            "gem5",
            ["src/cpu/minor/pipeline.hh", "src/cpu/minor/pipeline.cc"],
            "Implement pipeline_cycles(instructions, stages, issue_width, stalls). "
            "For an in-order ideal pipeline, empty work takes zero cycles; otherwise "
            "cycles are stages-1 plus ceil(instructions/issue_width), plus all explicit "
            "non-negative stall penalties. Validate that instructions is non-negative "
            "and stages and issue_width are positive integers.",
        ),
        "starter": """def pipeline_cycles(instructions: int, stages: int, issue_width: int, stalls: list[int]) -> int:
    raise NotImplementedError
""",
        "solution": """def pipeline_cycles(instructions: int, stages: int, issue_width: int, stalls: list[int]) -> int:
    if instructions < 0 or stages <= 0 or issue_width <= 0 or any(s < 0 for s in stalls):
        raise ValueError("invalid pipeline input")
    if instructions == 0:
        return 0
    return stages - 1 + (instructions + issue_width - 1) // issue_width + sum(stalls)
""",
        "tests": """import pytest
from model import pipeline_cycles

def test_latency_and_width():
    assert pipeline_cycles(1, 5, 1, []) == 5
    assert pipeline_cycles(10, 5, 2, []) == 9
    assert pipeline_cycles(10, 5, 2, [2, 3]) == 14
    assert pipeline_cycles(0, 5, 2, [4]) == 0

@pytest.mark.parametrize("args", [(-1, 5, 1, []), (1, 0, 1, []), (1, 5, 0, []), (1, 5, 1, [-1])])
def test_invalid(args):
    with pytest.raises(ValueError): pipeline_cycles(*args)
""",
    },
]


MODEL_TASKS = [
    {
        "task_id": "architecture-modeling-roofline",
        "meta": metadata(
            "architecture-modeling-roofline",
            "Architecture Modeling",
            "Timeloop and Accelergy exercises",
            ["python3", "pytest"],
            "timeloop",
            ["workspace/tutorial_exercises/02_interface_and_design_space_exploration_2024/1_specifications.ipynb"],
            "Implement roofline(operations, bytes_moved, peak_ops_per_cycle, "
            "bytes_per_cycle) returning arithmetic_intensity, attainable_ops_per_cycle, "
            "and cycles. The attainable rate is min(peak compute, intensity times memory "
            "bandwidth). Zero operations requires zero cycles; zero bytes means infinite "
            "intensity. Reject negative values and non-positive machine rates.",
        ),
        "starter": """def roofline(operations: float, bytes_moved: float, peak_ops_per_cycle: float, bytes_per_cycle: float) -> dict:
    raise NotImplementedError
""",
        "solution": """def roofline(operations: float, bytes_moved: float, peak_ops_per_cycle: float, bytes_per_cycle: float) -> dict:
    if operations < 0 or bytes_moved < 0 or peak_ops_per_cycle <= 0 or bytes_per_cycle <= 0:
        raise ValueError("invalid roofline input")
    intensity = float("inf") if bytes_moved == 0 else operations / bytes_moved
    rate = peak_ops_per_cycle if bytes_moved == 0 else min(peak_ops_per_cycle, intensity * bytes_per_cycle)
    cycles = 0.0 if operations == 0 else operations / rate
    return {"arithmetic_intensity": intensity, "attainable_ops_per_cycle": rate, "cycles": cycles}
""",
        "tests": """import math, pytest
from model import roofline

def test_memory_and_compute_bound():
    assert roofline(100, 100, 20, 4)["cycles"] == 25
    assert roofline(100, 10, 20, 4)["cycles"] == 5

def test_zero_bytes_and_work():
    result = roofline(10, 0, 5, 2)
    assert math.isinf(result["arithmetic_intensity"]) and result["cycles"] == 2
    assert roofline(0, 0, 5, 2)["cycles"] == 0

def test_invalid():
    with pytest.raises(ValueError): roofline(1, 1, 0, 1)
""",
    },
    {
        "task_id": "architecture-modeling-mesh-noc",
        "meta": metadata(
            "architecture-modeling-mesh-noc",
            "Architecture Modeling",
            "gem5",
            ["python3", "pytest"],
            "gem5",
            ["src/mem/ruby/network/garnet/GarnetNetwork.py", "src/mem/ruby/network/garnet/NetworkLink.hh"],
            "Implement mesh_latency(src, dst, width, height, router_cycles, link_cycles). "
            "Node IDs use row-major coordinates. Model deterministic XY routing: latency "
            "is one router traversal at every visited node plus one link traversal per "
            "Manhattan hop. Validate node IDs, dimensions, and non-negative cycle costs.",
        ),
        "starter": """def mesh_latency(src: int, dst: int, width: int, height: int, router_cycles: int, link_cycles: int) -> int:
    raise NotImplementedError
""",
        "solution": """def mesh_latency(src: int, dst: int, width: int, height: int, router_cycles: int, link_cycles: int) -> int:
    if width <= 0 or height <= 0 or not 0 <= src < width * height or not 0 <= dst < width * height:
        raise ValueError("invalid mesh node")
    if router_cycles < 0 or link_cycles < 0:
        raise ValueError("negative latency")
    sx, sy = src % width, src // width
    dx, dy = dst % width, dst // width
    hops = abs(sx - dx) + abs(sy - dy)
    return (hops + 1) * router_cycles + hops * link_cycles
""",
        "tests": """import pytest
from model import mesh_latency

def test_routes():
    assert mesh_latency(0, 0, 4, 3, 2, 1) == 2
    assert mesh_latency(0, 11, 4, 3, 2, 1) == 17
    assert mesh_latency(5, 6, 4, 3, 2, 3) == 7

def test_invalid():
    with pytest.raises(ValueError): mesh_latency(0, 12, 4, 3, 1, 1)
""",
    },
    {
        "task_id": "architecture-modeling-buffer",
        "meta": metadata(
            "architecture-modeling-buffer",
            "Architecture Modeling",
            "Accellera SystemC",
            ["python3", "pytest"],
            "systemc",
            ["examples/sysc/simple_fifo/simple_fifo.cpp"],
            "Implement simulate_fifo(capacity, events). events is a sequence of "
            "(produced, consumed) counts for each cycle. Consumption occurs from the "
            "cycle's starting occupancy, then production fills available slots. Return "
            "per-cycle occupancy plus total accepted, dropped, and underflow counts. "
            "Reject negative capacity or event counts.",
        ),
        "starter": """def simulate_fifo(capacity: int, events: list[tuple[int, int]]) -> dict:
    raise NotImplementedError
""",
        "solution": """def simulate_fifo(capacity: int, events: list[tuple[int, int]]) -> dict:
    if capacity < 0:
        raise ValueError("negative capacity")
    occupancy = accepted = dropped = underflow = 0
    trace = []
    for produced, consumed in events:
        if produced < 0 or consumed < 0:
            raise ValueError("negative event")
        actual_read = min(occupancy, consumed)
        underflow += consumed - actual_read
        occupancy -= actual_read
        actual_write = min(capacity - occupancy, produced)
        accepted += actual_write
        dropped += produced - actual_write
        occupancy += actual_write
        trace.append(occupancy)
    return {"occupancy": trace, "accepted": accepted, "dropped": dropped, "underflow": underflow}
""",
        "tests": """import pytest
from model import simulate_fifo

def test_trace_and_accounting():
    assert simulate_fifo(3, [(2, 1), (3, 1), (0, 4)]) == {
        "occupancy": [2, 3, 0], "accepted": 4, "dropped": 1, "underflow": 2}

def test_same_cycle_read_does_not_see_write():
    assert simulate_fifo(1, [(1, 1)])["underflow"] == 1

def test_invalid():
    with pytest.raises(ValueError): simulate_fifo(-1, [])
""",
    },
    {
        "task_id": "architecture-modeling-tiles",
        "meta": metadata(
            "architecture-modeling-tiles",
            "Architecture Modeling",
            "Timeloop and Accelergy exercises",
            ["python3", "pytest"],
            "timeloop",
            ["workspace/example_designs/example_designs/simple_weight_stationary/arch.yaml"],
            "Implement enumerate_tiles(extents, capacity). Return every positive integer "
            "tile shape whose dimensions divide the corresponding problem extent and "
            "whose element product is at most capacity. Order shapes lexicographically. "
            "Reject empty/non-positive extents and non-positive capacity.",
        ),
        "starter": """def enumerate_tiles(extents: tuple[int, ...], capacity: int) -> list[tuple[int, ...]]:
    raise NotImplementedError
""",
        "solution": """from itertools import product

def enumerate_tiles(extents: tuple[int, ...], capacity: int) -> list[tuple[int, ...]]:
    if not extents or any(value <= 0 for value in extents) or capacity <= 0:
        raise ValueError("invalid tiling input")
    divisors = [[d for d in range(1, value + 1) if value % d == 0] for value in extents]
    return sorted(shape for shape in product(*divisors) if _product(shape) <= capacity)

def _product(values):
    result = 1
    for value in values: result *= value
    return result
""",
        "tests": """import pytest
from model import enumerate_tiles

def test_divisibility_and_capacity():
    assert enumerate_tiles((4, 6), 8) == [
        (1, 1), (1, 2), (1, 3), (1, 6), (2, 1), (2, 2), (2, 3), (4, 1), (4, 2)]

def test_exact_capacity():
    assert (4, 4) in enumerate_tiles((8, 8), 16)
    assert (8, 4) not in enumerate_tiles((8, 8), 16)

def test_invalid():
    with pytest.raises(ValueError): enumerate_tiles((), 4)
""",
    },
    {
        "task_id": "architecture-modeling-energy",
        "meta": metadata(
            "architecture-modeling-energy",
            "Architecture Modeling",
            "Timeloop and Accelergy exercises",
            ["python3", "pytest"],
            "timeloop",
            ["workspace/cheatsheets/4_compound_component.yaml", "workspace/cheatsheets/3_architecture.yaml"],
            "Implement aggregate_energy(action_counts, energy_per_action). For every "
            "component and action count, multiply by the matching per-action energy and "
            "return component totals plus total. Reject negative counts or energies and "
            "raise KeyError when a requested component/action has no energy model. Do "
            "not count unused energy-table entries.",
        ),
        "starter": """def aggregate_energy(action_counts: dict, energy_per_action: dict) -> dict:
    raise NotImplementedError
""",
        "solution": """def aggregate_energy(action_counts: dict, energy_per_action: dict) -> dict:
    components = {}
    for component, actions in action_counts.items():
        subtotal = 0.0
        for action, count in actions.items():
            energy = energy_per_action[component][action]
            if count < 0 or energy < 0:
                raise ValueError("negative energy input")
            subtotal += count * energy
        components[component] = subtotal
    return {"components": components, "total": sum(components.values())}
""",
        "tests": """import pytest
from model import aggregate_energy

def test_aggregation():
    counts = {"mac": {"compute": 10}, "sram": {"read": 4, "write": 2}}
    table = {"mac": {"compute": 3}, "sram": {"read": .5, "write": 1}, "dram": {"read": 99}}
    assert aggregate_energy(counts, table) == {"components": {"mac": 30.0, "sram": 4.0}, "total": 34.0}

def test_missing_and_negative():
    with pytest.raises(KeyError): aggregate_energy({"x": {"read": 1}}, {})
    with pytest.raises(ValueError): aggregate_energy({"x": {"read": -1}}, {"x": {"read": 2}})
""",
    },
    {
        "task_id": "architecture-modeling-mapping",
        "meta": metadata(
            "architecture-modeling-mapping",
            "Architecture Modeling",
            "Timeloop and Accelergy exercises",
            ["python3", "pytest"],
            "timeloop",
            ["workspace/cheatsheets/3_architecture.yaml", "workspace/example_designs/example_designs/top.yaml.jinja2"],
            "Implement validate_mapping(problem, factors). Both dictionaries map "
            "dimension names to positive integers. Every problem dimension must appear "
            "in factors, no unknown factor dimensions are allowed, and each factor must "
            "divide the problem extent. Return a list of human-readable errors sorted by "
            "dimension, or an empty list for a valid mapping.",
        ),
        "starter": """def validate_mapping(problem: dict[str, int], factors: dict[str, int]) -> list[str]:
    raise NotImplementedError
""",
        "solution": """def validate_mapping(problem: dict[str, int], factors: dict[str, int]) -> list[str]:
    errors = []
    for name in sorted(set(problem) | set(factors)):
        if name not in problem:
            errors.append(f"{name}: unknown dimension")
        elif name not in factors:
            errors.append(f"{name}: missing factor")
        elif problem[name] <= 0 or factors[name] <= 0:
            errors.append(f"{name}: values must be positive")
        elif problem[name] % factors[name]:
            errors.append(f"{name}: factor does not divide extent")
    return errors
""",
        "tests": """from model import validate_mapping

def test_valid():
    assert validate_mapping({"M": 16, "N": 12}, {"M": 4, "N": 3}) == []

def test_all_error_classes_sorted():
    assert validate_mapping({"M": 16, "N": 10, "P": 4}, {"M": 3, "N": 0, "Z": 2}) == [
        "M: factor does not divide extent", "N: values must be positive",
        "P: missing factor", "Z: unknown dimension"]
""",
    },
    {
        "task_id": "architecture-modeling-sparse-traffic",
        "meta": metadata(
            "architecture-modeling-sparse-traffic",
            "Architecture Modeling",
            "Timeloop and Accelergy exercises",
            ["python3", "pytest"],
            "timeloop",
            ["workspace/tutorial_exercises/03_sparse_tensors_2021_isca/README.md"],
            "Implement sparse_storage(dense_elements, density, value_bytes, metadata_bits). "
            "Use ceil(dense_elements*density) stored nonzeros. Return nonzeros, data_bytes, "
            "metadata_bytes rounded up from bits, total_bytes, and compression_ratio "
            "(dense value bytes divided by sparse total bytes). For an empty sparse "
            "encoding return infinity as the ratio. Validate all inputs.",
        ),
        "starter": """def sparse_storage(dense_elements: int, density: float, value_bytes: int, metadata_bits: int) -> dict:
    raise NotImplementedError
""",
        "solution": """import math

def sparse_storage(dense_elements: int, density: float, value_bytes: int, metadata_bits: int) -> dict:
    if dense_elements < 0 or not 0 <= density <= 1 or value_bytes <= 0 or metadata_bits < 0:
        raise ValueError("invalid sparse tensor")
    nonzeros = math.ceil(dense_elements * density)
    data_bytes = nonzeros * value_bytes
    metadata_bytes = (nonzeros * metadata_bits + 7) // 8
    total = data_bytes + metadata_bytes
    ratio = float("inf") if total == 0 else dense_elements * value_bytes / total
    return {"nonzeros": nonzeros, "data_bytes": data_bytes, "metadata_bytes": metadata_bytes,
            "total_bytes": total, "compression_ratio": ratio}
""",
        "tests": """import math, pytest
from model import sparse_storage

def test_rounding():
    assert sparse_storage(10, .21, 2, 5) == {
        "nonzeros": 3, "data_bytes": 6, "metadata_bytes": 2,
        "total_bytes": 8, "compression_ratio": 2.5}

def test_empty():
    assert math.isinf(sparse_storage(10, 0, 4, 8)["compression_ratio"])

def test_invalid():
    with pytest.raises(ValueError): sparse_storage(4, 1.1, 2, 1)
""",
    },
    {
        "task_id": "architecture-modeling-queue",
        "meta": metadata(
            "architecture-modeling-queue",
            "Architecture Modeling",
            "Accellera SystemC",
            ["python3", "pytest"],
            "systemc",
            ["examples/sysc/simple_fifo/simple_fifo.cpp", "examples/sysc/pipe/main.cpp"],
            "Implement mm1_metrics(arrival_rate, service_rate). For a stable M/M/1 queue "
            "return utilization, average jobs in system, average jobs waiting, average "
            "system time, and average waiting time. Rates use the same time unit. Require "
            "arrival_rate >= 0, service_rate > 0, and arrival_rate < service_rate.",
        ),
        "starter": """def mm1_metrics(arrival_rate: float, service_rate: float) -> dict:
    raise NotImplementedError
""",
        "solution": """def mm1_metrics(arrival_rate: float, service_rate: float) -> dict:
    if arrival_rate < 0 or service_rate <= 0 or arrival_rate >= service_rate:
        raise ValueError("queue must be stable")
    rho = arrival_rate / service_rate
    system_time = 1 / (service_rate - arrival_rate)
    waiting_time = arrival_rate / (service_rate * (service_rate - arrival_rate))
    return {"utilization": rho, "jobs_system": arrival_rate * system_time,
            "jobs_waiting": arrival_rate * waiting_time, "system_time": system_time,
            "waiting_time": waiting_time}
""",
        "tests": """import pytest
from model import mm1_metrics

def test_metrics_and_little_law():
    m = mm1_metrics(2, 5)
    assert m["utilization"] == .4
    assert m["system_time"] == pytest.approx(1/3)
    assert m["waiting_time"] == pytest.approx(2/15)
    assert m["jobs_system"] == pytest.approx(2/3)
    assert m["jobs_waiting"] == pytest.approx(4/15)

def test_zero_arrivals():
    assert mm1_metrics(0, 4)["jobs_system"] == 0

def test_unstable():
    with pytest.raises(ValueError): mm1_metrics(5, 5)
""",
    },
]


RTL_IDS = [
    ("popcount3", "Prob009_popcount3"),
    ("mux2", "Prob017_mux2to1v"),
    ("dff8", "Prob034_dff8"),
    ("dff8-async-reset", "Prob047_dff8ar"),
    ("vector-concat", "Prob064_vector3"),
    ("truth-table", "Prob069_truthtable1"),
    ("thermostat", "Prob072_thermostat"),
    ("mux9", "Prob097_mux9to1v"),
]


def rtl_tasks() -> None:
    source_root = ROOT / "benchmarks" / "verilog-eval" / "dataset_spec-to-rtl"
    for slug, upstream_id in RTL_IDS:
        task_id = f"rtl-design-verilogeval-{slug}"
        prefix = f"dataset_spec-to-rtl/{upstream_id}"
        prompt = (source_root / f"{upstream_id}_prompt.txt").read_text(encoding="utf-8").strip()
        path = task_dir(task_id)
        spec = metadata(
            task_id,
            "RTL Design",
            "VerilogEval v2",
            ["Icarus Verilog 12", "SystemVerilog simulation"],
            "verilog-eval",
            [f"{prefix}_prompt.txt", f"{prefix}_test.sv", f"{prefix}_ref.sv"],
            prompt,
        )
        write(path / "task.json", json.dumps(spec, indent=2))
        write(path / "workspace" / "TopModule.sv", "// Implement TopModule here.")
        (path / "tests").mkdir(parents=True, exist_ok=True)
        shutil.copyfile(source_root / f"{upstream_id}_test.sv", path / "tests" / "tb.sv")
        shutil.copyfile(source_root / f"{upstream_id}_ref.sv", path / "tests" / "ref.sv")
        write(
            path / "tests" / "test.sh",
            f"""#!/bin/sh
set -eu
iverilog -g2012 -s tb -o /tmp/{task_id} /workspace/TopModule.sv /tests/ref.sv /tests/tb.sv
output=$(vvp -N /tmp/{task_id})
printf '%s\n' "$output"
printf '%s\n' "$output" | grep -Eq 'Mismatches: 0 in [1-9][0-9]* samples'
""",
        )
        write(
            path / "solution" / "solve.sh",
            """#!/bin/sh
set -eu
sed 's/module RefModule/module TopModule/' /tests/ref.sv > /workspace/TopModule.sv
""",
        )


DV_TASKS = [
    {
        "slug": "mux",
        "source": "Prob017_mux2to1v",
        "prompt": "Complete tb.sv as a self-checking testbench for dut. Exhaustively verify "
        "both select values and varied 8-bit inputs. The testbench must be named testbench, "
        "print PASS on success, call $fatal on any mismatch, and terminate.",
        "dut": "module dut(input [7:0] a,b, input sel, output [7:0] y); assign y = sel ? b : a; endmodule",
        "mutant": "module dut(input [7:0] a,b, input sel, output [7:0] y); assign y = sel ? a : b; endmodule",
        "gold": """module testbench;
reg [7:0] a,b; reg sel; wire [7:0] y; integer i;
dut d(a,b,sel,y);
initial begin
  for (i=0;i<32;i=i+1) begin
    a=i*7; b=8'hf0-i; sel=0; #1; if(y!==a) $fatal(1,"sel0");
    sel=1; #1; if(y!==b) $fatal(1,"sel1");
  end
  $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "popcount",
        "source": "Prob009_popcount3",
        "prompt": "Complete tb.sv as an exhaustive self-checking testbench for the 4-bit "
        "population-count dut. Cover all input values and calculate the expected result "
        "independently. Name the module testbench, print PASS, and use $fatal on mismatch.",
        "dut": "module dut(input [3:0] in, output [2:0] count); assign count=in[0]+in[1]+in[2]+in[3]; endmodule",
        "mutant": "module dut(input [3:0] in, output [2:0] count); assign count=in[0]+in[1]+in[2]; endmodule",
        "gold": """module testbench;
reg [3:0] in; wire [2:0] count; integer i; reg [2:0] expected;
dut d(in,count);
initial begin
  for(i=0;i<16;i=i+1) begin
    in=i; expected=((i>>0)&1)+((i>>1)&1)+((i>>2)&1)+((i>>3)&1);
    #1; if(count!==expected) $fatal(1,"count");
  end
  $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "dff-edge",
        "source": "Prob034_dff8",
        "prompt": "Complete tb.sv to verify that the 8-bit dut captures d only on positive "
        "clock edges, not negative edges or between edges. Name the module testbench, "
        "exercise multiple values, print PASS, and call $fatal on mismatch.",
        "dut": "module dut(input clk,input [7:0] d,output reg [7:0] q); initial q=0; always @(posedge clk) q<=d; endmodule",
        "mutant": "module dut(input clk,input [7:0] d,output reg [7:0] q); initial q=0; always @(negedge clk) q<=d; endmodule",
        "gold": """module testbench;
reg clk=0; reg [7:0] d=0; wire [7:0] q; dut u(clk,d,q);
always #5 clk=~clk;
initial begin
  #2 d=8'h12; #4; if(q!==8'h12) $fatal(1,"posedge capture");
  d=8'h34; #4; if(q!==8'h12) $fatal(1,"changed before edge");
  #1; if(q!==8'h12) $fatal(1,"negedge capture");
  #3 d=8'h56; #2; if(q!==8'h56) $fatal(1,"second edge");
  $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "async-reset",
        "source": "Prob047_dff8ar",
        "prompt": "Complete tb.sv to distinguish an active-high asynchronous reset from a "
        "synchronous reset in an 8-bit register. Verify data capture and reset asserted "
        "between clock edges. Name the module testbench, print PASS, and use $fatal.",
        "dut": "module dut(input clk,input rst,input [7:0] d,output reg [7:0] q); always @(posedge clk or posedge rst) if(rst) q<=0; else q<=d; endmodule",
        "mutant": "module dut(input clk,input rst,input [7:0] d,output reg [7:0] q); always @(posedge clk) if(rst) q<=0; else q<=d; endmodule",
        "gold": """module testbench;
reg clk=0,rst=0; reg [7:0] d=8'haa; wire [7:0] q; dut u(clk,rst,d,q);
always #5 clk=~clk;
initial begin
  #1 rst=1; #1; if(q!==0) $fatal(1,"initial reset"); rst=0;
  #3; #1; if(q!==8'haa) $fatal(1,"capture");
  #2 rst=1; #1; if(q!==0) $fatal(1,"reset not asynchronous");
  rst=0; d=8'h55; #7; if(q!==8'h55) $fatal(1,"recapture");
  $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "thermostat",
        "source": "Prob072_thermostat",
        "prompt": "Complete tb.sv as an exhaustive self-checking testbench for the thermostat "
        "dut ports mode, cold, hot, fan_req, heater, ac, and fan. Cover all 16 input "
        "combinations. Name the module testbench, print PASS, and call $fatal on mismatch.",
        "dut": "module dut(input mode,cold,hot,fan_req,output heater,ac,fan); assign heater=mode&cold; assign ac=~mode&hot; assign fan=heater|ac|fan_req; endmodule",
        "mutant": "module dut(input mode,cold,hot,fan_req,output heater,ac,fan); assign heater=mode&cold; assign ac=~mode&hot; assign fan=fan_req; endmodule",
        "gold": """module testbench;
reg mode,cold,hot,fan_req; wire heater,ac,fan; integer i; reg eh,ea,ef;
dut u(mode,cold,hot,fan_req,heater,ac,fan);
initial begin
 for(i=0;i<16;i=i+1) begin
  {mode,cold,hot,fan_req}=i; eh=mode&cold; ea=(~mode)&hot; ef=eh|ea|fan_req;
  #1; if({heater,ac,fan}!={eh,ea,ef}) $fatal(1,"thermostat");
 end
 $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "counter-wrap",
        "source": "Prob035_count1to10",
        "prompt": "Complete tb.sv to verify the synchronous reset and 1-through-10 wrap "
        "behavior of dut. Check every count value and at least two wraps. Name the module "
        "testbench, print PASS, and call $fatal on mismatch.",
        "dut": "module dut(input clk,reset,output reg [3:0] q); always @(posedge clk) if(reset||q==10) q<=1; else q<=q+1; endmodule",
        "mutant": "module dut(input clk,reset,output reg [3:0] q); always @(posedge clk) if(reset||q==9) q<=1; else q<=q+1; endmodule",
        "gold": """module testbench;
reg clk=0,reset=1; wire [3:0] q; integer i; reg [3:0] expected=1;
dut u(clk,reset,q); always #5 clk=~clk;
initial begin
 #6; if(q!==1) $fatal(1,"reset"); reset=0;
 for(i=0;i<22;i=i+1) begin
  @(posedge clk); #1; expected=(expected==10)?1:expected+1;
  if(q!==expected) $fatal(1,"count");
 end
 $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "parity",
        "source": "Prob064_vector3",
        "prompt": "Complete tb.sv as an exhaustive self-checking testbench for an 8-bit "
        "even-parity generator. Cover all 256 values and compute parity independently "
        "without using the DUT output. Name the module testbench, print PASS, and use $fatal.",
        "dut": "module dut(input [7:0] data,output parity); assign parity=^data; endmodule",
        "mutant": "module dut(input [7:0] data,output parity); assign parity=^data[6:0]; endmodule",
        "gold": """module testbench;
reg [7:0] data; wire parity; integer i,j; reg expected;
dut u(data,parity);
initial begin
 for(i=0;i<256;i=i+1) begin
  data=i; expected=0; for(j=0;j<8;j=j+1) expected=expected^((i>>j)&1);
  #1; if(parity!==expected) $fatal(1,"parity");
 end
 $display("PASS"); $finish;
end
endmodule""",
    },
    {
        "slug": "priority-encoder",
        "source": "Prob097_mux9to1v",
        "prompt": "Complete tb.sv as an exhaustive self-checking testbench for the 4-bit "
        "fixed-priority encoder dut. valid is high for nonzero req and index must select "
        "the lowest numbered asserted request. Name the module testbench, print PASS, and "
        "call $fatal on mismatch.",
        "dut": """module dut(input [3:0] req,output reg valid,output reg [1:0] index);
always @* begin valid=|req; casex(req) 4'b???1:index=0;4'b??10:index=1;4'b?100:index=2;default:index=3;endcase end endmodule""",
        "mutant": """module dut(input [3:0] req,output reg valid,output reg [1:0] index);
always @* begin valid=|req; casex(req) 4'b1???:index=3;4'b01??:index=2;4'b001?:index=1;default:index=0;endcase end endmodule""",
        "gold": """module testbench;
reg [3:0] req; wire valid; wire [1:0] index; integer i; reg [1:0] expected;
dut u(req,valid,index);
initial begin
 for(i=0;i<16;i=i+1) begin
  req=i;
  if(i&1) expected=0; else if(i&2) expected=1; else if(i&4) expected=2; else expected=3;
  #1; if(valid!==(i!=0)) $fatal(1,"valid");
  if(i!=0 && index!==expected) $fatal(1,"priority");
 end
 $display("PASS"); $finish;
end
endmodule""",
    },
]


def dv_tasks() -> None:
    for item in DV_TASKS:
        task_id = f"verification-verilogeval-{item['slug']}"
        source_id = str(item["source"])
        prefix = f"dataset_spec-to-rtl/{source_id}"
        path = task_dir(task_id)
        spec = metadata(
            task_id,
            "Verification (DV/FV)",
            "VerilogEval mutation extension",
            ["Icarus Verilog 12", "mutation testing"],
            "verilog-eval",
            [f"{prefix}_prompt.txt", f"{prefix}_test.sv", f"{prefix}_ref.sv"],
            str(item["prompt"]),
        )
        write(path / "task.json", json.dumps(spec, indent=2))
        write(path / "workspace" / "dut.sv", str(item["dut"]))
        write(path / "workspace" / "tb.sv", "module testbench;\n  // Write a self-checking testbench.\nendmodule")
        write(path / "tests" / "mutant.sv", str(item["mutant"]))
        write(
            path / "tests" / "test.sh",
            f"""#!/bin/sh
set -eu
iverilog -g2012 -s testbench -o /tmp/{task_id}-reference /workspace/dut.sv /workspace/tb.sv
vvp -N /tmp/{task_id}-reference | grep -q PASS
iverilog -g2012 -s testbench -o /tmp/{task_id}-mutant /tests/mutant.sv /workspace/tb.sv
if vvp -N /tmp/{task_id}-mutant >/dev/null 2>&1; then
  echo "mutation survived" >&2
  exit 1
fi
""",
        )
        write(
            path / "solution" / "solve.sh",
            "#!/bin/sh\nset -eu\ncat > /workspace/tb.sv <<'SV'\n"
            + str(item["gold"]).rstrip()
            + "\nSV",
        )


C_TASKS = [
    {
        "slug": "bitfield",
        "benchmark": "OpenTitan",
        "repo": "opentitan",
        "paths": ["sw/device/lib/base/bitfield.c", "sw/device/lib/base/bitfield.h"],
        "prompt": "Implement bitfield.c. bitfield_read32 extracts field.width bits at "
        "field.index. bitfield_write32 replaces exactly that field. Width may be 0 through "
        "32; width 32 is valid only at index 0. Out-of-range fields leave writes unchanged "
        "and reads return 0. Avoid undefined shifts.",
        "header": """#include <stdint.h>
typedef struct { uint8_t index; uint8_t width; } bitfield_t;
uint32_t bitfield_read32(uint32_t value, bitfield_t field);
uint32_t bitfield_write32(uint32_t value, bitfield_t field, uint32_t field_value);""",
        "starter": """#include "utility.h"
uint32_t bitfield_read32(uint32_t value, bitfield_t field) { (void)value; (void)field; return 0; }
uint32_t bitfield_write32(uint32_t value, bitfield_t field, uint32_t field_value) { (void)field; (void)field_value; return value; }""",
        "solution": """#include "utility.h"
static int valid(bitfield_t f){ return f.width<=32 && f.index<=31 && (unsigned)f.index+f.width<=32; }
static uint32_t mask(bitfield_t f){ return f.width==32?UINT32_MAX:(f.width==0?0:((UINT32_C(1)<<f.width)-1)); }
uint32_t bitfield_read32(uint32_t v, bitfield_t f){ return valid(f)?(v>>f.index)&mask(f):0; }
uint32_t bitfield_write32(uint32_t v, bitfield_t f, uint32_t x){ if(!valid(f))return v; uint32_t m=mask(f); return (v&~(m<<f.index))|((x&m)<<f.index); }""",
        "test": """#include <assert.h>
#include <stdint.h>
#include "utility.h"
int main(void){
 assert(bitfield_read32(0xdeadbeef,(bitfield_t){8,8})==0xbe);
 assert(bitfield_write32(0xffffffff,(bitfield_t){8,8},0x12)==0xffff12ff);
 assert(bitfield_read32(0x12345678,(bitfield_t){0,32})==0x12345678);
 assert(bitfield_write32(7,(bitfield_t){4,0},3)==7);
 assert(bitfield_read32(7,(bitfield_t){31,2})==0);
 assert(bitfield_write32(7,(bitfield_t){31,2},0)==7);
 return 0;
}""",
    },
    {
        "slug": "endian",
        "benchmark": "Zephyr RTOS",
        "repo": "zephyr",
        "paths": ["include/zephyr/sys/byteorder.h", "tests/kernel/common/src/byteorder.c"],
        "prompt": "Implement portable unaligned little- and big-endian 16/32-bit loads and "
        "stores in utility.c using the API in utility.h. Do not cast byte pointers to wider "
        "integer pointers and do not depend on host byte order or alignment.",
        "header": """#include <stdint.h>
uint16_t load_le16(const void *p); uint32_t load_le32(const void *p); uint32_t load_be32(const void *p);
void store_le16(void *p,uint16_t v); void store_le32(void *p,uint32_t v); void store_be32(void *p,uint32_t v);""",
        "starter": """#include "utility.h"
uint16_t load_le16(const void*p){(void)p;return 0;} uint32_t load_le32(const void*p){(void)p;return 0;} uint32_t load_be32(const void*p){(void)p;return 0;}
void store_le16(void*p,uint16_t v){(void)p;(void)v;} void store_le32(void*p,uint32_t v){(void)p;(void)v;} void store_be32(void*p,uint32_t v){(void)p;(void)v;}""",
        "solution": """#include "utility.h"
uint16_t load_le16(const void*p){const uint8_t*b=p;return (uint16_t)b[0]|((uint16_t)b[1]<<8);}
uint32_t load_le32(const void*p){const uint8_t*b=p;return (uint32_t)b[0]|((uint32_t)b[1]<<8)|((uint32_t)b[2]<<16)|((uint32_t)b[3]<<24);}
uint32_t load_be32(const void*p){const uint8_t*b=p;return ((uint32_t)b[0]<<24)|((uint32_t)b[1]<<16)|((uint32_t)b[2]<<8)|b[3];}
void store_le16(void*p,uint16_t v){uint8_t*b=p;b[0]=v;b[1]=v>>8;}
void store_le32(void*p,uint32_t v){uint8_t*b=p;for(int i=0;i<4;i++)b[i]=v>>(8*i);}
void store_be32(void*p,uint32_t v){uint8_t*b=p;for(int i=0;i<4;i++)b[i]=v>>(8*(3-i));}""",
        "test": """#include <assert.h>
#include <stdint.h>
#include <string.h>
#include "utility.h"
int main(void){uint8_t b[9]={0}; store_le16(b+1,0x1234); assert(b[1]==0x34&&b[2]==0x12&&load_le16(b+1)==0x1234);
 store_le32(b+1,0x89abcdef); assert(load_le32(b+1)==0x89abcdef); assert(b[1]==0xef&&b[4]==0x89);
 store_be32(b+3,0x10203040); assert(load_be32(b+3)==0x10203040); assert(b[3]==0x10&&b[6]==0x40); return 0;}""",
    },
    {
        "slug": "ring-buffer",
        "benchmark": "Zephyr RTOS",
        "repo": "zephyr",
        "paths": ["lib/utils/ring_buffer.c", "tests/lib/ringbuffer/src/main.c"],
        "prompt": "Implement the fixed-capacity byte ring buffer in utility.c. rb_put and "
        "rb_get return the number of bytes transferred, support wraparound and partial "
        "transfers, preserve FIFO order, and never allocate. rb_init resets caller-owned "
        "storage. A zero-capacity ring must behave safely.",
        "header": """#include <stddef.h>
#include <stdint.h>
typedef struct {uint8_t *data; size_t capacity,head,tail,size;} ring_buffer_t;
void rb_init(ring_buffer_t*r,uint8_t*storage,size_t capacity);
size_t rb_put(ring_buffer_t*r,const uint8_t*src,size_t count);
size_t rb_get(ring_buffer_t*r,uint8_t*dst,size_t count);""",
        "starter": """#include "utility.h"
void rb_init(ring_buffer_t*r,uint8_t*s,size_t c){(void)r;(void)s;(void)c;}
size_t rb_put(ring_buffer_t*r,const uint8_t*s,size_t n){(void)r;(void)s;(void)n;return 0;}
size_t rb_get(ring_buffer_t*r,uint8_t*d,size_t n){(void)r;(void)d;(void)n;return 0;}""",
        "solution": """#include "utility.h"
void rb_init(ring_buffer_t*r,uint8_t*s,size_t c){r->data=s;r->capacity=c;r->head=r->tail=r->size=0;}
size_t rb_put(ring_buffer_t*r,const uint8_t*s,size_t n){size_t done=0;while(done<n&&r->size<r->capacity){r->data[r->tail]=s[done++];r->tail=(r->tail+1)%r->capacity;r->size++;}return done;}
size_t rb_get(ring_buffer_t*r,uint8_t*d,size_t n){size_t done=0;while(done<n&&r->size){d[done++]=r->data[r->head];r->head=(r->head+1)%r->capacity;r->size--;}return done;}""",
        "test": """#include <assert.h>
#include <string.h>
#include "utility.h"
int main(void){uint8_t s[4],out[6],a[]={1,2,3,4},b[]={5,6};ring_buffer_t r;rb_init(&r,s,4);
 assert(rb_put(&r,a,4)==4&&rb_put(&r,b,2)==0);assert(rb_get(&r,out,2)==2);
 assert(rb_put(&r,b,2)==2);assert(rb_get(&r,out+2,4)==4);
 uint8_t expected[]={1,2,3,4,5,6};assert(!memcmp(out,expected,6));
 rb_init(&r,s,0);assert(rb_put(&r,a,1)==0&&rb_get(&r,out,1)==0);return 0;}""",
    },
    {
        "slug": "crc16",
        "benchmark": "Zephyr RTOS",
        "repo": "zephyr",
        "paths": ["subsys/crc/crc16_sw.c", "tests/unit/crc/main.c"],
        "prompt": "Implement crc16_ccitt in utility.c using polynomial 0x1021, caller-supplied "
        "initial state, no reflection, and no final xor. Process each byte most-significant "
        "bit first. Support zero length and incremental use without tables or allocation.",
        "header": """#include <stddef.h>
#include <stdint.h>
uint16_t crc16_ccitt(uint16_t initial,const uint8_t*data,size_t length);""",
        "starter": """#include "utility.h"
uint16_t crc16_ccitt(uint16_t initial,const uint8_t*data,size_t length){(void)data;(void)length;return initial;}""",
        "solution": """#include "utility.h"
uint16_t crc16_ccitt(uint16_t crc,const uint8_t*d,size_t n){for(size_t i=0;i<n;i++){crc^=(uint16_t)d[i]<<8;for(int b=0;b<8;b++)crc=(crc&0x8000)?(uint16_t)((crc<<1)^0x1021):(uint16_t)(crc<<1);}return crc;}""",
        "test": """#include <assert.h>
#include <string.h>
#include "utility.h"
int main(void){const uint8_t*s=(const uint8_t*)"123456789";assert(crc16_ccitt(0xffff,s,9)==0x29b1);
 uint16_t a=crc16_ccitt(0xffff,s,4);a=crc16_ccitt(a,s+4,5);assert(a==0x29b1);
 assert(crc16_ccitt(0x1234,s,0)==0x1234);return 0;}""",
    },
    {
        "slug": "saturating",
        "benchmark": "OpenTitan",
        "repo": "opentitan",
        "paths": ["sw/device/lib/base/math.c", "sw/device/lib/base/math.h"],
        "prompt": "Implement saturating unsigned 32-bit add, subtract, and multiply in "
        "utility.c. Clamp overflow to UINT32_MAX and subtraction underflow to zero. The "
        "implementation must be defined by C11 for all input values.",
        "header": """#include <stdint.h>
uint32_t sat_add_u32(uint32_t a,uint32_t b); uint32_t sat_sub_u32(uint32_t a,uint32_t b); uint32_t sat_mul_u32(uint32_t a,uint32_t b);""",
        "starter": """#include "utility.h"
uint32_t sat_add_u32(uint32_t a,uint32_t b){return a+b;} uint32_t sat_sub_u32(uint32_t a,uint32_t b){return a-b;} uint32_t sat_mul_u32(uint32_t a,uint32_t b){return a*b;}""",
        "solution": """#include <stdint.h>
#include "utility.h"
uint32_t sat_add_u32(uint32_t a,uint32_t b){return UINT32_MAX-a<b?UINT32_MAX:a+b;}
uint32_t sat_sub_u32(uint32_t a,uint32_t b){return a<b?0:a-b;}
uint32_t sat_mul_u32(uint32_t a,uint32_t b){return b&&a>UINT32_MAX/b?UINT32_MAX:a*b;}""",
        "test": """#include <assert.h>
#include <stdint.h>
#include "utility.h"
int main(void){assert(sat_add_u32(10,20)==30);assert(sat_add_u32(UINT32_MAX,1)==UINT32_MAX);
 assert(sat_sub_u32(4,9)==0&&sat_sub_u32(9,4)==5);
 assert(sat_mul_u32(0,UINT32_MAX)==0);assert(sat_mul_u32(65536,65536)==UINT32_MAX);assert(sat_mul_u32(12,11)==132);return 0;}""",
    },
    {
        "slug": "fixed-point",
        "benchmark": "Zephyr RTOS",
        "repo": "zephyr",
        "paths": ["tests/unit/intmath/main.c", "include/zephyr/sys/math_extras.h"],
        "prompt": "Implement signed Q16.16 multiplication and division in utility.c. Round "
        "multiplication to nearest with ties away from zero. Division truncates toward "
        "zero. Saturate results to INT32_MIN/MAX and report division by zero as the signed "
        "saturation matching the numerator (zero divided by zero returns zero).",
        "header": """#include <stdint.h>
int32_t q16_mul(int32_t a,int32_t b); int32_t q16_div(int32_t a,int32_t b);""",
        "starter": """#include "utility.h"
int32_t q16_mul(int32_t a,int32_t b){(void)a;(void)b;return 0;} int32_t q16_div(int32_t a,int32_t b){(void)a;(void)b;return 0;}""",
        "solution": """#include <limits.h>
#include <stdint.h>
#include "utility.h"
static int32_t clamp(int64_t x){return x>INT32_MAX?INT32_MAX:x<INT32_MIN?INT32_MIN:(int32_t)x;}
int32_t q16_mul(int32_t a,int32_t b){int64_t p=(int64_t)a*b; p+=p>=0?32768:-32768; return clamp(p/65536);}
int32_t q16_div(int32_t a,int32_t b){if(!b)return a>0?INT32_MAX:a<0?INT32_MIN:0;return clamp(((int64_t)a*65536)/b);}""",
        "test": """#include <assert.h>
#include <limits.h>
#include "utility.h"
int main(void){assert(q16_mul(98304,131072)==196608);assert(q16_mul(-98304,131072)==-196608);
 assert(q16_div(196608,131072)==98304);assert(q16_div(-196608,131072)==-98304);
 assert(q16_mul(INT32_MAX,INT32_MAX)==INT32_MAX);assert(q16_div(1,0)==INT32_MAX);assert(q16_div(-1,0)==INT32_MIN);assert(q16_div(0,0)==0);return 0;}""",
    },
    {
        "slug": "intrusive-list",
        "benchmark": "Zephyr RTOS",
        "repo": "zephyr",
        "paths": ["tests/unit/list/dlist.c", "include/zephyr/sys/dlist.h"],
        "prompt": "Implement the intrusive doubly linked list API in utility.c. list_init uses "
        "a circular sentinel. Support append, prepend, remove, pop_front, and pop_back. "
        "Removal must leave the removed node self-linked; popping an empty list returns "
        "NULL. Do not allocate memory.",
        "header": """#include <stddef.h>
typedef struct list_node {struct list_node*prev,*next;} list_node_t;
void list_init(list_node_t*h); void list_append(list_node_t*h,list_node_t*n); void list_prepend(list_node_t*h,list_node_t*n);
void list_remove(list_node_t*n); list_node_t*list_pop_front(list_node_t*h); list_node_t*list_pop_back(list_node_t*h);""",
        "starter": """#include "utility.h"
void list_init(list_node_t*h){(void)h;} void list_append(list_node_t*h,list_node_t*n){(void)h;(void)n;} void list_prepend(list_node_t*h,list_node_t*n){(void)h;(void)n;}
void list_remove(list_node_t*n){(void)n;} list_node_t*list_pop_front(list_node_t*h){(void)h;return 0;} list_node_t*list_pop_back(list_node_t*h){(void)h;return 0;}""",
        "solution": """#include "utility.h"
void list_init(list_node_t*h){h->next=h->prev=h;}
static void between(list_node_t*a,list_node_t*b,list_node_t*n){n->prev=a;n->next=b;a->next=n;b->prev=n;}
void list_append(list_node_t*h,list_node_t*n){between(h->prev,h,n);} void list_prepend(list_node_t*h,list_node_t*n){between(h,h->next,n);}
void list_remove(list_node_t*n){n->prev->next=n->next;n->next->prev=n->prev;n->next=n->prev=n;}
list_node_t*list_pop_front(list_node_t*h){if(h->next==h)return 0;list_node_t*n=h->next;list_remove(n);return n;}
list_node_t*list_pop_back(list_node_t*h){if(h->prev==h)return 0;list_node_t*n=h->prev;list_remove(n);return n;}""",
        "test": """#include <assert.h>
#include "utility.h"
int main(void){list_node_t h,a,b,c;list_init(&h);assert(!list_pop_front(&h));list_append(&h,&a);list_append(&h,&b);list_prepend(&h,&c);
 assert(list_pop_front(&h)==&c&&c.next==&c&&c.prev==&c);list_remove(&a);assert(a.next==&a&&h.next==&b);
 assert(list_pop_back(&h)==&b);assert(h.next==&h&&h.prev==&h);return 0;}""",
    },
    {
        "slug": "hash",
        "benchmark": "Zephyr RTOS",
        "repo": "zephyr",
        "paths": ["tests/lib/hash_function/src/main.c", "include/zephyr/sys/hash_function.h"],
        "prompt": "Implement 32-bit FNV-1a in utility.c with offset basis 2166136261 and "
        "prime 16777619. fnv1a32 hashes a complete buffer. fnv1a32_update continues from "
        "a caller-provided state so chunked and one-shot hashing match. Support zero length "
        "and arbitrary byte values with defined uint32_t wraparound.",
        "header": """#include <stddef.h>
#include <stdint.h>
uint32_t fnv1a32_update(uint32_t state,const void*data,size_t length); uint32_t fnv1a32(const void*data,size_t length);""",
        "starter": """#include "utility.h"
uint32_t fnv1a32_update(uint32_t s,const void*d,size_t n){(void)d;(void)n;return s;} uint32_t fnv1a32(const void*d,size_t n){(void)d;(void)n;return 0;}""",
        "solution": """#include "utility.h"
uint32_t fnv1a32_update(uint32_t s,const void*d,size_t n){const uint8_t*p=d;for(size_t i=0;i<n;i++){s^=p[i];s*=UINT32_C(16777619);}return s;}
uint32_t fnv1a32(const void*d,size_t n){return fnv1a32_update(UINT32_C(2166136261),d,n);}""",
        "test": """#include <assert.h>
#include <string.h>
#include "utility.h"
int main(void){const char*s="hello";assert(fnv1a32(s,5)==0x4f9f2cab);assert(fnv1a32("",0)==2166136261u);
 uint32_t h=fnv1a32("he",2);h=fnv1a32_update(h,"llo",3);assert(h==fnv1a32(s,5));
 unsigned char b[]={0,255,1};assert(fnv1a32(b,3)==fnv1a32_update(2166136261u,b,3));return 0;}""",
    },
]


def c_tasks() -> None:
    for item in C_TASKS:
        task_id = f"software-{item['repo']}-{item['slug']}"
        path = task_dir(task_id)
        spec = metadata(
            task_id,
            "Software Development",
            str(item["benchmark"]),
            ["gcc", "C11"],
            str(item["repo"]),
            list(item["paths"]),
            str(item["prompt"]),
        )
        write(path / "task.json", json.dumps(spec, indent=2))
        write(path / "workspace" / "utility.h", str(item["header"]))
        write(path / "workspace" / "utility.c", str(item["starter"]))
        write(path / "tests" / "test_utility.c", str(item["test"]))
        write(
            path / "tests" / "test.sh",
            f"""#!/bin/sh
set -eu
gcc -std=c11 -Wall -Wextra -Werror -pedantic -I/workspace \
  /workspace/utility.c /tests/test_utility.c -o /tmp/{task_id}
/tmp/{task_id}
""",
        )
        write(
            path / "solution" / "solve.sh",
            "#!/bin/sh\nset -eu\ncat > /workspace/utility.c <<'C'\n"
            + str(item["solution"]).rstrip()
            + "\nC",
        )


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--group",
        action="append",
        choices=["architecture", "modeling", "rtl", "verification", "software"],
        help="Materialize only selected groups; defaults to all.",
    )
    return parser.parse_args()


def main() -> None:
    selected = set(parse_args().group or ["architecture", "modeling", "rtl", "verification", "software"])
    if "architecture" in selected:
        for spec in ARCH_TASKS:
            python_task(spec)
    if "modeling" in selected:
        for spec in MODEL_TASKS:
            python_task(spec)
    if "rtl" in selected:
        rtl_tasks()
    if "verification" in selected:
        dv_tasks()
    if "software" in selected:
        c_tasks()
    print(f"materialized {', '.join(sorted(selected))} chip task groups")


if __name__ == "__main__":
    main()

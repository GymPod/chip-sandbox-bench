# Chip-design task sources

This directory contains the inspectable source form of the 50-task chip-design
dataset, balanced at ten tasks per discipline. Each task has:

- `task.json`: discipline, upstream benchmark provenance, prompt, and tool gate.
- `workspace/`: files visible to the model at the start of the task.
- `tests/`: the independent executable verifier.
- `solution/solve.sh`: a deterministic gold solution for harness validation.

Build the runner dataset and provenance manifest with:

```bash
python3 scripts/expand_chip_tasks.py
python3 scripts/build_chip_tasks.py
```

Confirm the checked-in artifacts are reproducible with:

```bash
python3 scripts/build_chip_tasks.py --check
```

The sample intentionally uses CPU-only, open-source gates. Architecture and
modeling tasks use Python, C++, SystemC, and YAML checks; RTL and verification
tasks use Icarus Verilog and Yosys; software tasks use portable C11. KernelBench
is vendored for a later GPU lane, while RealBench formal scoring and full
RISC-V DV flows require tool or license environments beyond this MicroVM image.

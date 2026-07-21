# Chip-design task sources

This directory contains the inspectable source form of the ten-task chip-design
smoke dataset. Each task has:

- `task.json`: discipline, upstream benchmark provenance, prompt, and tool gate.
- `workspace/`: files visible to the model at the start of the task.
- `tests/`: the independent executable verifier.
- `solution/solve.sh`: a deterministic gold solution for harness validation.

Build the runner dataset and provenance manifest with:

```bash
python3 scripts/build_chip_tasks.py
```

Confirm the checked-in artifacts are reproducible with:

```bash
python3 scripts/build_chip_tasks.py --check
```

The initial sample intentionally uses CPU-only, open-source gates. KernelBench
is vendored for a later GPU lane, while RealBench formal scoring and full
RISC-V DV flows require tool or license environments beyond this MicroVM smoke
image.

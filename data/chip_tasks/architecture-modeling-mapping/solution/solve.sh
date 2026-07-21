#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
def validate_mapping(problem: dict[str, int], factors: dict[str, int]) -> list[str]:
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
PY

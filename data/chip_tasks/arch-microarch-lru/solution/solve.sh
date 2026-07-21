#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
class LRUSet:
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
PY

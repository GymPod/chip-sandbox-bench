#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
class GShare:
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
PY

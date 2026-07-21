#!/bin/sh
set -eu
cat > /workspace/model.py <<'PY'
class FullyAssociativeTLB:
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
PY

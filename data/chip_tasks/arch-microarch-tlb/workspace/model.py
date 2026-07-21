class FullyAssociativeTLB:
    def __init__(self, entries: int, page_size: int):
        raise NotImplementedError
    def lookup(self, virtual_address: int):
        raise NotImplementedError
    def insert(self, vpn: int, ppn: int) -> None:
        raise NotImplementedError
    def invalidate(self, vpn: int) -> None:
        raise NotImplementedError

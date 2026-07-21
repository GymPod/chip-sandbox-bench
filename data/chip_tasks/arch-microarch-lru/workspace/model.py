class LRUSet:
    def __init__(self, ways: int):
        raise NotImplementedError
    def touch(self, line: int) -> None:
        raise NotImplementedError
    def invalidate(self, line: int) -> None:
        raise NotImplementedError
    def victim(self) -> int:
        raise NotImplementedError

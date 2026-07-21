class GShare:
    def __init__(self, entries: int, history_bits: int):
        raise NotImplementedError

    def predict(self, pc: int) -> bool:
        raise NotImplementedError

    def update(self, pc: int, taken: bool) -> None:
        raise NotImplementedError

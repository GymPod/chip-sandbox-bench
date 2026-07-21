"""Small ArchGym-style multi-objective design-space exploration helper."""


def pareto_frontier(candidates: list[dict[str, object]]) -> list[str]:
    """Return IDs for designs not dominated on latency, energy, and area."""
    raise NotImplementedError

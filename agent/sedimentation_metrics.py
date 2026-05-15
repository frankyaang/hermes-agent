"""Atomic counters for knowledge sedimentation observability."""
from __future__ import annotations

METRIC_NAMES = frozenset({
    "candidate_detected",
    "routed_to_memory",
    "routed_to_skill",
    "routed_to_knowledge",
    "pending_created",
    "knowledge_write_success",
    "knowledge_write_failed",
    "no_action_with_reason",
    "replay_success",
    "replay_failed",
    "blocked",
})


class SedimentationMetrics:
    def __init__(self) -> None:
        self._counters: dict[str, int] = {name: 0 for name in METRIC_NAMES}

    def increment(self, metric_name: str, count: int = 1) -> None:
        if metric_name not in self._counters:
            raise KeyError(f"Unknown metric: {metric_name!r}")
        self._counters[metric_name] += count

    def snapshot(self) -> dict[str, int]:
        return dict(self._counters)

    def reset(self) -> None:
        for k in self._counters:
            self._counters[k] = 0


_default_metrics = SedimentationMetrics()


def increment(metric_name: str, count: int = 1) -> None:
    """Increment module-level metrics singleton (non-fatal for unknown names)."""
    try:
        _default_metrics.increment(metric_name, count)
    except KeyError:
        pass


def snapshot() -> dict[str, int]:
    return _default_metrics.snapshot()

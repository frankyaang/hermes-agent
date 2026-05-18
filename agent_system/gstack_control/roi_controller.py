"""
ROI controller — computes redacted ROI metrics per phase.
All inputs pass through metrics_redaction before any use.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from .performance_budget import within_budget
from .metrics_redaction import redact_dict


@dataclass
class ROIResult:
    phase_id: str
    within_budget: bool
    latency_ms: int
    # token counts are preserved as integers (not secrets)
    input_tokens: int
    output_tokens: int
    # free-form metadata is redacted before storage
    metadata: dict[str, Any]


def compute(
    phase_id: str,
    latency_ms: int,
    input_tokens: int,
    output_tokens: int,
    metadata: dict[str, Any] | None = None,
) -> ROIResult:
    """Compute ROI for a phase invocation. metadata is redacted."""
    clean_meta = redact_dict(metadata or {})
    ok = within_budget(phase_id, latency_ms, input_tokens, output_tokens)
    return ROIResult(
        phase_id=phase_id,
        within_budget=ok,
        latency_ms=latency_ms,
        input_tokens=input_tokens,
        output_tokens=output_tokens,
        metadata=clean_meta,
    )

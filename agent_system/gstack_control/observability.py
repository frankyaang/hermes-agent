"""
Observability — structured logging for gstack_control.
Re-uses hermes_logging.setup_logging() and its RedactingFormatter.
"""
from __future__ import annotations

import logging

from hermes_logging import setup_logging

setup_logging()

logger = logging.getLogger("agent_system.gstack_control")


def log_decision(phase_id: str, mode: str, risk_level: str) -> None:
    logger.info(
        "gstack_control decision phase=%s mode=%s risk=%s",
        phase_id,
        mode,
        risk_level,
    )


def log_dry_run(phase_id: str, risk_level: str, mode: str) -> None:
    logger.info(
        "gstack_control dry_run phase=%s risk=%s -> mode=%s",
        phase_id,
        risk_level,
        mode,
    )


def log_rollback(reason: str) -> None:
    logger.warning("gstack_control rollback triggered reason=%r", reason)

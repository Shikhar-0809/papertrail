"""Anomaly rule evaluation service.

Evaluates rules and writes alerts to audit_log. Does NOT block requests —
blocking is vault_service's responsibility.
"""

import logging
from dataclasses import dataclass
from datetime import datetime

import aiosqlite

from backend.config import RAPID_REQUEST_MAX_COUNT
from backend.services.audit_helpers import write_audit

logger = logging.getLogger(__name__)


@dataclass
class AnomalyContext:
    exam_id: str
    center_id: str
    center_code: str
    ip_address: str
    requested_at: datetime
    release_at: datetime
    request_count_last_minute: int


@dataclass
class Alert:
    rule_id: str
    severity: str
    human_readable: str
    details: dict
    action_taken: str


# --- Rule implementations ---------------------------------------------------

def _evaluate_r001(context: AnomalyContext) -> Alert | None:
    """R001 — Premature access attempt."""
    if context.requested_at >= context.release_at:
        return None
    delta = context.release_at - context.requested_at
    minutes_early = int(delta.total_seconds() / 60)
    return Alert(
        rule_id="R001",
        severity="CRITICAL",
        human_readable=(
            f"Center {context.center_code} attempted key access "
            f"{minutes_early} minutes early from {context.ip_address}"
        ),
        details={"minutes_early": minutes_early, "action": "key_blocked"},
        action_taken="key_blocked",
    )


def _evaluate_r002(_context: AnomalyContext) -> Alert | None:
    # MVP: no IP allowlist configured, rule disabled
    return None


def _evaluate_r003(context: AnomalyContext) -> Alert | None:
    """R003 — Rapid repeat requests."""
    count = context.request_count_last_minute
    if count < RAPID_REQUEST_MAX_COUNT:
        return None
    return Alert(
        rule_id="R003",
        severity="HIGH",
        human_readable=(
            f"Center {context.center_code} made {count} key requests "
            f"in under 60 seconds from {context.ip_address}"
        ),
        details={"request_count": count, "window_seconds": 60},
        action_taken="flagged",
    )


_RULE_EVALUATORS = {
    "R001": _evaluate_r001,
    "R002": _evaluate_r002,
    "R003": _evaluate_r003,
}

# --- Public API -------------------------------------------------------------

async def evaluate(
    rule_id: str,
    context: AnomalyContext,
    db: aiosqlite.Connection,
) -> Alert | None:
    """Evaluate a single rule. Writes to audit_log if alert fires."""
    evaluator = _RULE_EVALUATORS.get(rule_id)
    if evaluator is None:
        logger.error("Unknown rule_id requested: %s", rule_id)
        return None
    alert = evaluator(context)
    if alert is not None:
        await write_audit(
            event_type=f"anomaly_{alert.rule_id.lower()}",
            severity=alert.severity,
            human_readable=alert.human_readable,
            exam_id=context.exam_id,
            center_id=context.center_id,
            ip_address=context.ip_address,
            db=db,
            rule_id=alert.rule_id,
            details=alert.details,
        )
        logger.warning(
            "Alert fired: rule=%s severity=%s center=%s exam=%s ip=%s",
            alert.rule_id, alert.severity,
            context.center_code, context.exam_id, context.ip_address,
        )
    return alert


async def evaluate_all(
    context: AnomalyContext,
    db: aiosqlite.Connection,
) -> list[Alert]:
    """Evaluate all rules except R001 (vault_service calls R001 separately)."""
    fired: list[Alert] = []
    for rule_id in ("R002", "R003"):
        alert = await evaluate(rule_id, context, db)
        if alert is not None:
            fired.append(alert)
    return fired

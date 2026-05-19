"""
ExecutionContract skill — pipeline node wrapper。

接收 decision_gate 输出的路由表 + 可选的人工确认 JSON，
生成 DecisionCard 列表、ExecutionContract 列表和 FollowUpList。
"""
from __future__ import annotations

import json
import logging
from pathlib import Path

from agent_system.schemas.weekly_schemas import (
    ConsensusLedger,
    DecisionCard,
    ExecutionContract,
    FollowUpItem,
    FollowUpList,
    Issue,
)

logger = logging.getLogger(__name__)

_AUDIT_PATH = Path(__file__).parents[3] / "agent_system" / "audit" / "audit.jsonl"


def run(
    issues_json: str,
    routes_json: str,
    confirmation_json: str | None = None,
    pipeline_run_id: str = "unknown",
) -> str:
    """
    Pipeline node entry point。

    Args:
        issues_json: List[Issue]-like 字典列表 JSON
        routes_json: {issue_id: route} 字典 JSON（来自 decision_gate）
        confirmation_json: {issue_id: {decision, execution_owner, committed_action,
                             deadline, acceptance_criteria, verification_evidence}} JSON
        pipeline_run_id: 当前 pipeline 运行 ID

    Returns:
        JSON 字符串，含 decision_cards, execution_contracts, incomplete_commitments,
        consensus_ledger, follow_up_list, metrics
    """
    try:
        raw_issues = json.loads(issues_json)
        routes = json.loads(routes_json)
    except json.JSONDecodeError as e:
        logger.error("execution_contract: invalid JSON input: %s", e)
        return json.dumps({"error": "invalid_json"})

    confirmations: dict = {}
    if confirmation_json:
        try:
            confirmations = json.loads(confirmation_json)
        except json.JSONDecodeError:
            logger.warning("execution_contract: invalid confirmation_json, treating as empty")

    issues: list[Issue] = []
    for item in raw_issues:
        if not isinstance(item, dict):
            continue
        try:
            issues.append(Issue(
                title=str(item.get("title", "")),
                background=str(item.get("background", "")),
                source_ref=str(item.get("source_ref", "weekly_unknown")),
                urgency=item.get("urgency", "medium"),
                options=item.get("options", []),
                recommended_option=item.get("recommended_option"),
                owner_candidate=item.get("owner_candidate"),
                acceptance_criteria=item.get("acceptance_criteria"),
                issue_id=item.get("issue_id", ""),
            ))
        except Exception as e:
            logger.warning("execution_contract: skipping malformed issue: %s", e)

    decision_cards: list[dict] = []
    execution_contracts: list[dict] = []
    ledger = ConsensusLedger(total_issues=len(issues))
    follow_up_list = FollowUpList()

    for issue in issues:
        route = routes.get(issue.issue_id, "need_more_info")

        if route == "fake_closure_detected":
            ledger.skipped_fake_closure.append({
                "issue_id": issue.issue_id,
                "title": issue.title,
                "reason": "fake_closure_detected",
            })
            continue

        if route == "decision_agenda":
            card = DecisionCard(
                issue_id=issue.issue_id,
                title=issue.title,
                recommended_option=issue.recommended_option or "",
                acceptance_criteria=issue.acceptance_criteria or "",
                owner_candidate=issue.owner_candidate,
                route="decision_agenda",
                confirmed_by_human=False,
            )
            decision_cards.append({
                "card_id": card.card_id,
                "issue_id": card.issue_id,
                "title": card.title,
                "recommended_option": card.recommended_option,
                "acceptance_criteria": card.acceptance_criteria,
                "owner_candidate": card.owner_candidate,
                "route": card.route,
                "confirmed_by_human": card.confirmed_by_human,
            })

            conf = confirmations.get(issue.issue_id)
            if conf and isinstance(conf, dict):
                contract = ExecutionContract(
                    issue_id=issue.issue_id,
                    title=issue.title,
                    decision=str(conf.get("decision", "")),
                    execution_owner=conf.get("execution_owner") or None,
                    committed_action=conf.get("committed_action") or None,
                    deadline=conf.get("deadline") or None,
                    acceptance_criteria=conf.get("acceptance_criteria") or None,
                    verification_evidence=conf.get("verification_evidence") or None,
                    confirmed_by_human=True,
                )
                missing = contract.missing_fields()
                if missing:
                    contract.current_status = "incomplete"
                    ledger.incomplete_commitments.append({
                        "issue_id": issue.issue_id,
                        "title": issue.title,
                        "missing_fields": missing,
                    })
                    follow_up_list.items.append(FollowUpItem(
                        issue_id=issue.issue_id,
                        title=issue.title,
                        status="incomplete",
                        owner=contract.execution_owner,
                        deadline=contract.deadline,
                        missing_fields=missing,
                    ))
                else:
                    contract.current_status = "confirmed"
                    ledger.confirmed_contracts.append(contract)
                    follow_up_list.items.append(FollowUpItem(
                        issue_id=issue.issue_id,
                        title=issue.title,
                        status="confirmed",
                        owner=contract.execution_owner,
                        deadline=contract.deadline,
                    ))
                execution_contracts.append(_contract_to_dict(contract))
            else:
                pending = ExecutionContract(
                    issue_id=issue.issue_id,
                    title=issue.title,
                    current_status="pending_confirmation",
                    original_recommended_option=issue.recommended_option,
                    acceptance_criteria=issue.acceptance_criteria,
                )
                ledger.pending_contracts.append(pending)
                follow_up_list.items.append(FollowUpItem(
                    issue_id=issue.issue_id,
                    title=issue.title,
                    status="pending_confirmation",
                ))

    metrics = {
        "total_issues": ledger.total_issues,
        "decision_agenda_count": len(decision_cards),
        "confirmed_count": len(ledger.confirmed_contracts),
        "pending_count": len(ledger.pending_contracts),
        "fake_closure_count": len(ledger.skipped_fake_closure),
        "incomplete_count": len(ledger.incomplete_commitments),
    }

    logger.info("execution_contract: processed %d issues, metrics=%s", len(issues), metrics)

    # 将 pending contracts 持久化到 WeeklyLedgerStore，供 Feishu callback 查找。
    if ledger.pending_contracts:
        try:
            import os as _os
            from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore
            _home = _os.getenv("HERMES_HOME")
            _store = WeeklyLedgerStore(home=Path(_home) if _home else None)
            _persistent = _store.load()
            _existing_ids = {c.issue_id for c in _persistent.pending_contracts}
            for _p in ledger.pending_contracts:
                if _p.issue_id not in _existing_ids:
                    _persistent.pending_contracts.append(_p)
            _persistent.total_issues = max(_persistent.total_issues, ledger.total_issues)
            _store.save(_persistent)
        except Exception as exc:
            logger.warning("execution_contract: failed to persist pending to ledger: %s", exc)

    return json.dumps({
        "decision_cards": decision_cards,
        "execution_contracts": execution_contracts,
        "incomplete_commitments": ledger.incomplete_commitments,
        "consensus_ledger": {
            "confirmed_count": len(ledger.confirmed_contracts),
            "pending_count": len(ledger.pending_contracts),
            "fake_closure_count": len(ledger.skipped_fake_closure),
            "skipped_fake_closure": ledger.skipped_fake_closure,
            "incomplete_commitments": ledger.incomplete_commitments,
            "total_issues": ledger.total_issues,
        },
        "follow_up_list": {
            "items": [
                {
                    "issue_id": i.issue_id,
                    "title": i.title,
                    "status": i.status,
                    "owner": i.owner,
                    "deadline": i.deadline,
                    "missing_fields": i.missing_fields,
                }
                for i in follow_up_list.items
            ],
            "pending_count": follow_up_list.pending_count(),
        },
        "metrics": metrics,
    }, ensure_ascii=False)


def _contract_to_dict(c: ExecutionContract) -> dict:
    return {
        "contract_id": c.contract_id,
        "issue_id": c.issue_id,
        "title": c.title,
        "decision": c.decision,
        "execution_owner": c.execution_owner,
        "committed_action": c.committed_action,
        "deadline": c.deadline,
        "acceptance_criteria": c.acceptance_criteria,
        "verification_evidence": c.verification_evidence,
        "current_status": c.current_status,
        "confirmed_by_human": c.confirmed_by_human,
        "missing_fields": c.missing_fields(),
    }

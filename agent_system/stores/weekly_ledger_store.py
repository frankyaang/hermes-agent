"""
WeeklyLedgerStore — 持久化 ConsensusLedger 到 HERMES_HOME/weekly_flow/ledger.json。

- load(): 文件不存在时返回空 ledger
- save(): 原子写（.tmp + rename）
- apply_event(): 幂等处理 ConfirmationEvent
  * fake_closure route → 返回 None，不写 ledger
  * 已有 event_id → 返回已有合同，不重复写
  * 缺字段 → status=incomplete，写 ledger
  * 全字段 → status=confirmed，写 ledger
"""
from __future__ import annotations

import json
import logging
from dataclasses import asdict
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from agent_system.schemas.weekly_schemas import (
        ConfirmationEvent,
        ConsensusLedger,
        ExecutionContract,
        Issue,
    )

logger = logging.getLogger(__name__)

_FAKE_CLOSURE_ROUTE = "fake_closure_detected"


class WeeklyLedgerStore:
    def __init__(self, home: Path | None = None):
        if home is None:
            from hermes_constants import get_hermes_home
            home = get_hermes_home()
        self._path = home / "weekly_flow" / "ledger.json"

    def load(self) -> "ConsensusLedger":
        from agent_system.schemas.weekly_schemas import ConsensusLedger, ExecutionContract
        if not self._path.exists():
            return ConsensusLedger()
        try:
            data = json.loads(self._path.read_text(encoding="utf-8"))
            ledger = ConsensusLedger(
                total_issues=data.get("total_issues", 0),
                skipped_fake_closure=data.get("skipped_fake_closure", []),
                incomplete_commitments=data.get("incomplete_commitments", []),
            )
            for c in data.get("confirmed_contracts", []):
                ledger.confirmed_contracts.append(_dict_to_contract(c))
            for c in data.get("pending_contracts", []):
                ledger.pending_contracts.append(_dict_to_contract(c))
            return ledger
        except Exception as e:
            logger.warning("weekly_ledger: load failed (%s), returning empty ledger", e)
            return ConsensusLedger()

    def save(self, ledger: "ConsensusLedger") -> None:
        self._path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self._path.with_suffix(".tmp")
        data = {
            "total_issues": ledger.total_issues,
            "confirmed_contracts": [_contract_to_dict(c) for c in ledger.confirmed_contracts],
            "pending_contracts": [_contract_to_dict(c) for c in ledger.pending_contracts],
            "skipped_fake_closure": ledger.skipped_fake_closure,
            "incomplete_commitments": ledger.incomplete_commitments,
        }
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self._path)

    def apply_event(
        self,
        event: "ConfirmationEvent",
        issue: "Issue",
        route: str = "decision_agenda",
    ) -> "ExecutionContract | None":
        """
        幂等处理确认事件。
        - fake_closure_detected route → 返回 None
        - 已有 event_id → 返回已有合同
        - 否则创建新合同，保存 ledger
        """
        if route == _FAKE_CLOSURE_ROUTE:
            return None

        from agent_system.schemas.weekly_schemas import ExecutionContract

        ledger = self.load()

        # 幂等检查：event_id 已存在 → 返回已有合同
        for contract in ledger.confirmed_contracts + ledger.pending_contracts:
            if getattr(contract, "event_id", None) == event.event_id:
                return contract

        # 创建新合同
        contract = ExecutionContract(
            issue_id=issue.issue_id,
            title=issue.title,
            decision=event.decision,
            execution_owner=event.execution_owner,
            committed_action=event.committed_action,
            deadline=event.deadline,
            acceptance_criteria=event.acceptance_criteria,
            verification_evidence=event.verification_evidence,
            confirmed_by_human=True,
        )
        contract.event_id = event.event_id  # 存储用于幂等校验

        missing = contract.missing_fields()
        if missing:
            contract.current_status = "incomplete"
            ledger.incomplete_commitments.append({
                "issue_id": issue.issue_id,
                "contract_id": contract.contract_id,
                "missing_fields": missing,
            })
        else:
            contract.current_status = "confirmed"
            ledger.confirmed_contracts.append(contract)

        ledger.total_issues = max(ledger.total_issues, 1)
        self.save(ledger)
        return contract


def _contract_to_dict(c: "ExecutionContract") -> dict:
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
        "original_recommended_option": c.original_recommended_option,
        "event_id": getattr(c, "event_id", ""),
        "created_at": c.created_at,
        "followup_at": c.followup_at,
    }


def _dict_to_contract(d: dict) -> "ExecutionContract":
    from agent_system.schemas.weekly_schemas import ExecutionContract
    c = ExecutionContract(
        contract_id=d.get("contract_id", ""),
        issue_id=d.get("issue_id", ""),
        title=d.get("title", ""),
        decision=d.get("decision", ""),
        execution_owner=d.get("execution_owner"),
        committed_action=d.get("committed_action"),
        deadline=d.get("deadline"),
        acceptance_criteria=d.get("acceptance_criteria"),
        verification_evidence=d.get("verification_evidence"),
        current_status=d.get("current_status", "pending_confirmation"),
        confirmed_by_human=d.get("confirmed_by_human", False),
        original_recommended_option=d.get("original_recommended_option"),
        created_at=d.get("created_at", ""),
        followup_at=d.get("followup_at", ""),
    )
    c.event_id = d.get("event_id", "")
    return c

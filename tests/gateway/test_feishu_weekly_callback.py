"""
Feishu _on_card_action_trigger → weekly_confirmation 路由级测试

验证：
  1. weekly_confirmation type → 调度 _handle_weekly_confirmation_action（不走 approval handler）
  2. weekly_confirmation 不干扰 approval button 路由
  3. approval button 原有行为不回归
  4. loop 不可用时安全返回空响应
  5. callback → handler → ledger 状态变化（异步集成）
  6. fake_closure 拦截（handler 层）
  7. event_id 幂等（handler 层）
"""
from __future__ import annotations

import asyncio
import importlib.util
import sys
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

# ──────────────────────────────────────────────────────────────────────────────
# Feishu 导入环境设置（复用 test_feishu_approval_buttons.py 的模式）
# ──────────────────────────────────────────────────────────────────────────────

_repo = str(Path(__file__).resolve().parents[2])
if _repo not in sys.path:
    sys.path.insert(0, _repo)


def _ensure_feishu_mocks():
    if importlib.util.find_spec("lark_oapi") is None and "lark_oapi" not in sys.modules:
        mod = MagicMock()
        for name in ("lark_oapi", "lark_oapi.api.im.v1",
                     "lark_oapi.event", "lark_oapi.event.callback_type"):
            sys.modules.setdefault(name, mod)
    if importlib.util.find_spec("aiohttp") is None and "aiohttp" not in sys.modules:
        aio = MagicMock()
        sys.modules.setdefault("aiohttp", aio)
        sys.modules.setdefault("aiohttp.web", aio.web)


_ensure_feishu_mocks()

from gateway.config import PlatformConfig
import gateway.platforms.feishu as feishu_module
from gateway.platforms.feishu import FeishuAdapter


class _FakeCallBackCard:
    def __init__(self):
        self.type = None
        self.data = None


class _FakeP2Response:
    def __init__(self):
        self.card = None


@pytest.fixture(autouse=False)
def _patch_card_types(monkeypatch):
    monkeypatch.setattr(feishu_module, "P2CardActionTriggerResponse", _FakeP2Response)
    monkeypatch.setattr(feishu_module, "CallBackCard", _FakeCallBackCard)


def _make_adapter() -> FeishuAdapter:
    config = PlatformConfig(enabled=True)
    adapter = FeishuAdapter(config)
    adapter._client = MagicMock()
    return adapter


def _make_card_action_data(action_value: dict) -> SimpleNamespace:
    return SimpleNamespace(
        event=SimpleNamespace(
            token="tok_abc",
            context=SimpleNamespace(open_chat_id="oc_12345"),
            operator=SimpleNamespace(open_id="ou_user1"),
            action=SimpleNamespace(tag="button", value=action_value),
        ),
    )


def _close_submitted_coro(coro, _loop):
    coro.close()
    return SimpleNamespace(add_done_callback=lambda *_a, **_k: None)


# ──────────────────────────────────────────────────────────────────────────────
# 1. weekly_confirmation → 调度 _handle_weekly_confirmation_action
# ──────────────────────────────────────────────────────────────────────────────

def test_weekly_confirmation_routes_to_handler(_patch_card_types):
    adapter = _make_adapter()
    adapter._loop = MagicMock()
    adapter._loop.is_closed = MagicMock(return_value=False)

    data = _make_card_action_data({
        "type": "weekly_confirmation",
        "issue_id": "ISS-001",
        "event_id": "EVT-001",
        "decision": "采用方案A",
    })

    with patch.object(adapter, "_handle_weekly_confirmation_action",
                      new_callable=AsyncMock) as mock_handler:
        with patch("asyncio.run_coroutine_threadsafe", side_effect=_close_submitted_coro):
            response = adapter._on_card_action_trigger(data)

    # 返回空响应（不带 card 内容）
    assert response is not None
    assert response.card is None
    # _handle_weekly_confirmation_action 被调用（通过 _submit_on_loop → run_coroutine_threadsafe）


# ──────────────────────────────────────────────────────────────────────────────
# 2. weekly_confirmation 不干扰 approval button 路由
# ──────────────────────────────────────────────────────────────────────────────

def test_weekly_confirmation_does_not_call_approval_handler(_patch_card_types):
    adapter = _make_adapter()
    adapter._loop = MagicMock()
    adapter._loop.is_closed = MagicMock(return_value=False)

    data = _make_card_action_data({
        "type": "weekly_confirmation",
        "issue_id": "ISS-001",
    })

    with patch.object(adapter, "_handle_approval_card_action") as mock_approval:
        with patch("asyncio.run_coroutine_threadsafe", side_effect=_close_submitted_coro):
            adapter._on_card_action_trigger(data)

    mock_approval.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# 3. approval button 原有行为不回归
# ──────────────────────────────────────────────────────────────────────────────

def test_approval_button_still_routes_to_approval_handler(_patch_card_types):
    adapter = _make_adapter()
    adapter._loop = MagicMock()
    adapter._loop.is_closed = MagicMock(return_value=False)

    data = _make_card_action_data({
        "hermes_action": "approve_once",
        "approval_id": 42,
    })

    with patch.object(adapter, "_handle_approval_card_action",
                      return_value=_FakeP2Response()) as mock_approval:
        adapter._on_card_action_trigger(data)

    mock_approval.assert_called_once()


# ──────────────────────────────────────────────────────────────────────────────
# 4. loop 不可用时安全返回空响应
# ──────────────────────────────────────────────────────────────────────────────

def test_loop_not_ready_returns_safe_response_for_weekly(_patch_card_types):
    adapter = _make_adapter()
    adapter._loop = None  # loop 未就绪

    data = _make_card_action_data({
        "type": "weekly_confirmation",
        "issue_id": "ISS-001",
    })

    with patch("asyncio.run_coroutine_threadsafe") as mock_submit:
        response = adapter._on_card_action_trigger(data)

    assert response is not None
    mock_submit.assert_not_called()


# ──────────────────────────────────────────────────────────────────────────────
# 5. callback → handler → ledger 状态变化（完整异步集成）
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_writes_to_ledger(tmp_path, monkeypatch):
    """P0-5：_handle_weekly_confirmation_action 真实写 ledger，不 mock handle_weekly_confirmation_payload。

    步骤：
    1. HERMES_HOME → tmp_path（WeeklyLedgerStore 使用 tmp_path）
    2. 预先写入 pending contract（模拟 execution_contract skill 的输出）
    3. 调用 _handle_weekly_confirmation_action（不 mock handler）
    4. reload store，验证 confirmed_contracts 有 1 个合同
    """
    from agent_system.schemas.weekly_schemas import ConsensusLedger, ExecutionContract
    from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # 预填充 pending contract（模拟 execution_contract skill 写入）
    store = WeeklyLedgerStore(home=tmp_path)
    pending = ExecutionContract(
        issue_id="ISS-CB-001",
        title="X11 定价策略",
        current_status="pending_confirmation",
        original_recommended_option="方案B：涨价 8%",
        acceptance_criteria="Q3 毛利达标",
    )
    ldr = ConsensusLedger(total_issues=1)
    ldr.pending_contracts.append(pending)
    store.save(ldr)

    action_value = {
        "type": "weekly_confirmation",
        "issue_id": "ISS-CB-001",
        "event_id": "EVT-CB-REAL-001",
        "decision": "采用方案B",
        "execution_owner": "张三",
        "committed_action": "完成定价文档",
        "deadline": "2026-06-30",
        "acceptance_criteria": "Q3 毛利达标",
        "verification_evidence": "review 截图",
    }

    adapter = _make_adapter()
    # 不 mock handle_weekly_confirmation_payload，让真实链路跑
    await adapter._handle_weekly_confirmation_action(action_value)

    # 验证 ledger 状态
    reloaded = WeeklyLedgerStore(home=tmp_path).load()
    assert len(reloaded.confirmed_contracts) == 1, (
        "_handle_weekly_confirmation_action 必须将 pending → confirmed 写入 ledger"
    )
    assert reloaded.confirmed_contracts[0].current_status == "confirmed"
    assert reloaded.confirmed_contracts[0].execution_owner == "张三"
    assert reloaded.confirmed_contracts[0].issue_id == "ISS-CB-001"


@pytest.mark.asyncio
async def test_handler_fake_closure_real_ledger(tmp_path, monkeypatch):
    """P0-5：fake_closure issue 经 callback 后，ledger confirmed_contracts 仍为 0。"""
    from agent_system.schemas.weekly_schemas import ConsensusLedger, ExecutionContract
    from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    # 预填充 fake_closure 的 pending contract
    store = WeeklyLedgerStore(home=tmp_path)
    pending = ExecutionContract(
        issue_id="ISS-FAKE-CB",
        title="持续跟进问题",
        current_status="pending_confirmation",
        original_recommended_option="持续跟进并推动清库",
        acceptance_criteria=None,
    )
    ldr = ConsensusLedger(total_issues=1)
    ldr.pending_contracts.append(pending)
    store.save(ldr)

    action_value = {
        "type": "weekly_confirmation",
        "issue_id": "ISS-FAKE-CB",
        "event_id": "EVT-FAKE-CB",
        "decision": "持续跟进",
        "execution_owner": None,
        "committed_action": None,
        "deadline": None,
        "acceptance_criteria": None,
        "verification_evidence": None,
    }

    adapter = _make_adapter()
    await adapter._handle_weekly_confirmation_action(action_value)

    reloaded = WeeklyLedgerStore(home=tmp_path).load()
    assert len(reloaded.confirmed_contracts) == 0, (
        "fake_closure issue 不应生成 confirmed contract"
    )


@pytest.mark.asyncio
async def test_handler_idempotent_real_ledger(tmp_path, monkeypatch):
    """P0-5：相同 event_id 两次 callback → ledger 中仍只有 1 个 confirmed contract。"""
    from agent_system.schemas.weekly_schemas import ConsensusLedger, ExecutionContract
    from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore

    monkeypatch.setenv("HERMES_HOME", str(tmp_path))

    store = WeeklyLedgerStore(home=tmp_path)
    pending = ExecutionContract(
        issue_id="ISS-IDEM-CB",
        title="幂等测试议题",
        current_status="pending_confirmation",
        original_recommended_option="方案A",
        acceptance_criteria="通过 review",
    )
    ldr = ConsensusLedger(total_issues=1)
    ldr.pending_contracts.append(pending)
    store.save(ldr)

    action_value = {
        "type": "weekly_confirmation",
        "issue_id": "ISS-IDEM-CB",
        "event_id": "EVT-IDEM-FIXED",
        "decision": "采用方案A",
        "execution_owner": "李四",
        "committed_action": "完成文档",
        "deadline": "2026-07-01",
        "acceptance_criteria": "通过 review",
        "verification_evidence": "截图",
    }

    adapter = _make_adapter()
    await adapter._handle_weekly_confirmation_action(action_value)
    await adapter._handle_weekly_confirmation_action(action_value)  # 同 event_id 第二次

    reloaded = WeeklyLedgerStore(home=tmp_path).load()
    assert len(reloaded.confirmed_contracts) == 1, (
        "相同 event_id 的两次 callback 应幂等，只生成 1 个 confirmed contract"
    )


# ──────────────────────────────────────────────────────────────────────────────
# 6. fake_closure 拦截（handler 层）
# ──────────────────────────────────────────────────────────────────────────────

@pytest.mark.asyncio
async def test_handler_intercepts_fake_closure(tmp_path):
    from agent_system.adapters.weekly_confirmation_handler import handle_weekly_confirmation_payload
    from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore
    from agent_system.schemas.weekly_schemas import Issue

    fake_issue = Issue(
        issue_id="ISS-FAKE",
        title="持续跟进问题",
        background="库存积压",
        recommended_option="持续跟进并推动落实",
        options=[],
        owner_candidate=None,
        urgency="low",
        source_ref="w20",
    )

    payload = {"action": {"value": {
        "type": "weekly_confirmation",
        "issue_id": "ISS-FAKE",
        "event_id": "EVT-FAKE",
        "decision": "持续跟进",
        "execution_owner": None,
        "committed_action": None,
        "deadline": None,
        "acceptance_criteria": None,
        "verification_evidence": None,
    }}}

    store = WeeklyLedgerStore(home=tmp_path)
    result = handle_weekly_confirmation_payload(
        payload, issue_lookup={"ISS-FAKE": fake_issue}, store=store
    )
    assert result is None

    ledger = store.load()
    assert len(ledger.confirmed_contracts) == 0


# ──────────────────────────────────────────────────────────────────────────────
# 7. event_id 幂等（相同 event_id 两次调用只产生一个合同）
# ──────────────────────────────────────────────────────────────────────────────

def test_handler_event_id_idempotent(tmp_path):
    from agent_system.adapters.weekly_confirmation_handler import handle_weekly_confirmation_payload
    from agent_system.stores.weekly_ledger_store import WeeklyLedgerStore
    from agent_system.schemas.weekly_schemas import Issue

    issue = Issue(
        issue_id="ISS-IDEM",
        title="幂等测试议题",
        background="背景",
        recommended_option="方案A",
        options=["方案A"],
        owner_candidate="李四",
        urgency="medium",
        source_ref="w20",
    )
    payload = {"action": {"value": {
        "type": "weekly_confirmation",
        "issue_id": "ISS-IDEM",
        "event_id": "EVT-FIXED-999",
        "decision": "采用方案A",
        "execution_owner": "李四",
        "committed_action": "完成文档",
        "deadline": "2026-07-01",
        "acceptance_criteria": "通过 review",
        "verification_evidence": "截图",
    }}}

    store = WeeklyLedgerStore(home=tmp_path)
    r1 = handle_weekly_confirmation_payload(payload, {"ISS-IDEM": issue}, store)
    r2 = handle_weekly_confirmation_payload(payload, {"ISS-IDEM": issue}, store)

    assert r1 is not None
    assert r2 is not None
    assert r1.contract_id == r2.contract_id

    ledger = store.load()
    assert len(ledger.confirmed_contracts) == 1

"""
Weekly Flow Entrypoints Tests (P0-1)

验证 weekly_flow 入口策略：
  1. weekly_flow pipeline DAG 结构正确（3 节点，依赖关系完整）
  2. create_weekly_shannon_job 存在于 cron/jobs.py（cron 批处理入口）
  3. create_weekly_shannon_job 创建的 job 含 weekly_flow 标识
  4. weekly_flow 节点不在 routes.json 单独声明 production_ready；以 readiness_manifest 为准

设计原则：weekly_flow 是 cron-triggered 批处理流，无 HTTP API 外部入口。
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

_REPO = str(Path(__file__).resolve().parents[2])
if _REPO not in sys.path:
    sys.path.insert(0, _REPO)

_ROUTES_PATH = (
    Path(__file__).resolve().parents[2]
    / "agent_system"
    / "scheduler"
    / "main_scheduler"
    / "routes.json"
)


# ──────────────────────────────────────────────────────────────────────────────
# 1. pipeline DAG 结构
# ──────────────────────────────────────────────────────────────────────────────

def test_weekly_flow_pipeline_dag_structure():
    """routes.json 中 weekly_flow 有 3 个节点且 DAG 依赖正确。"""
    with open(_ROUTES_PATH) as f:
        routes = json.load(f)

    weekly_nodes = [n for n in routes["pipelines"] if n["pipeline_id"] == "weekly_flow"]
    assert len(weekly_nodes) == 3, f"weekly_flow 应有 3 个节点，实际 {len(weekly_nodes)}"

    nodes_by_step = {n["step"]: n for n in weekly_nodes}
    assert nodes_by_step[1]["node"] == "issue_extractor"
    assert nodes_by_step[2]["node"] == "decision_gate"
    assert nodes_by_step[3]["node"] == "execution_contract"

    # 依赖关系
    assert "issue_extractor" in nodes_by_step[2].get("depends_on", [])
    assert "decision_gate" in nodes_by_step[3].get("depends_on", [])


# ──────────────────────────────────────────────────────────────────────────────
# 2. routes.json 不单独授予 production_ready
# ──────────────────────────────────────────────────────────────────────────────

def test_weekly_flow_nodes_defer_production_ready_to_manifest():
    """weekly_flow 外部依赖未满足时，routes.json 不能绕过 manifest 标 ready。"""
    with open(_ROUTES_PATH) as f:
        routes = json.load(f)

    weekly_nodes = [n for n in routes["pipelines"] if n["pipeline_id"] == "weekly_flow"]
    for node in weekly_nodes:
        assert node.get("production_ready") is False
        assert "readiness_manifest" in node.get("readiness_reason", "")


# ──────────────────────────────────────────────────────────────────────────────
# 3. create_weekly_shannon_job 存在（RED：函数未实现时 FAIL）
# ──────────────────────────────────────────────────────────────────────────────

def test_create_weekly_shannon_job_exists():
    """cron/jobs.py 必须有 create_weekly_shannon_job 函数（cron 批处理入口）。"""
    from cron.jobs import create_weekly_shannon_job  # ImportError → FAIL until P0-1 implemented
    assert callable(create_weekly_shannon_job)


# ──────────────────────────────────────────────────────────────────────────────
# 4. create_weekly_shannon_job 调用 create_job 且传入 weekly_flow 信息
# ──────────────────────────────────────────────────────────────────────────────

def test_create_weekly_shannon_job_invokes_create_job():
    """create_weekly_shannon_job 内部调用 create_job，且 prompt 含 weekly_flow 相关内容。"""
    from cron.jobs import create_weekly_shannon_job
    import cron.jobs as jobs_mod
    from unittest.mock import patch, call

    captured = {}

    def _fake_create_job(prompt, schedule, **kwargs):
        captured["prompt"] = prompt
        captured["schedule"] = schedule
        captured["kwargs"] = kwargs
        return {"job_id": "test-job-id"}

    with patch.object(jobs_mod, "create_job", side_effect=_fake_create_job):
        result = create_weekly_shannon_job(
            raw_material="本周议题：X11 定价\n负责人：张三",
            schedule="0 9 * * 1",
        )

    assert "prompt" in captured, "create_job 未被调用"
    # prompt 或参数中含有 weekly_flow 相关内容
    all_str = str(captured["prompt"]) + str(captured.get("kwargs", ""))
    assert "weekly_flow" in all_str or "weekly" in all_str.lower() or "议题" in all_str, (
        "create_weekly_shannon_job 的 job 应包含 weekly 相关内容"
    )

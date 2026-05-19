"""Experience Layer Runtime ACL Tests

Verifies that write_to_layer() ACL is correctly enforced:
- hermes_main can write system_mem
- other callers cannot write system_mem → staging
- each expert can write its own expert_mem
- gstack cannot write expert_mem → staging
- each skill can write its own skill_mem
- gstack cannot write skill_mem → staging
"""
from __future__ import annotations

import pytest
from pathlib import Path


def test_hermes_main_can_write_system_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer

    result = write_to_layer(
        layer="system_mem",
        content="system experience line",
        caller_id="hermes_main",
        hermes_home=tmp_path,
    )

    assert result.success, "hermes_main must be allowed to write system_mem"
    assert result.staging_id == "", "no staging on success"


def test_non_hermes_main_denied_system_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer
    from agent.staging_store import list_staging

    result = write_to_layer(
        layer="system_mem",
        content="unauthorized write attempt",
        caller_id="some_other_caller",
        hermes_home=tmp_path,
    )

    assert not result.success, "non-hermes_main must be denied"
    assert result.staging_id, "denied content must be in staging"
    entries = list_staging(hermes_home=tmp_path)
    assert any(e["staging_id"] == result.staging_id for e in entries)


def test_expert_writes_own_expert_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer

    result = write_to_layer(
        layer="expert_mem",
        content="user_analyst experience",
        caller_id="user_analyst",
        expert_id="user_analyst",
        hermes_home=tmp_path,
    )

    assert result.success, "expert must be allowed to write its own expert_mem"


def test_gstack_denied_expert_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer
    from agent.staging_store import list_staging

    result = write_to_layer(
        layer="expert_mem",
        content="gstack lesson attempt",
        caller_id="gstack_bridge",
        expert_id="audit_expert",
        hermes_home=tmp_path,
    )

    assert not result.success, "gstack must not write expert_mem"
    assert result.staging_id, "denied gstack content must go to staging"


def test_wrong_expert_denied_expert_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer

    result = write_to_layer(
        layer="expert_mem",
        content="builder writes into audit",
        caller_id="builder_expert",
        expert_id="audit_expert",
        hermes_home=tmp_path,
    )

    assert not result.success, "builder_expert must not write audit_expert mem"


def test_skill_writes_own_skill_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer

    result = write_to_layer(
        layer="skill_mem",
        content="sql_skill execution history",
        caller_id="sql_skill",
        skill_id="sql_skill",
        hermes_home=tmp_path,
    )

    assert result.success


def test_gstack_denied_skill_mem(tmp_path):
    from agent_system.sedimentation.experience_layer import write_to_layer

    result = write_to_layer(
        layer="skill_mem",
        content="gstack playbook attempt",
        caller_id="gstack_control",
        skill_id="sql_skill",
        hermes_home=tmp_path,
    )

    assert not result.success
    assert result.staging_id


def test_acl_denied_content_never_discarded(tmp_path):
    """All ACL-denied writes must appear in staging — never silently dropped."""
    from agent_system.sedimentation.experience_layer import write_to_layer
    from agent.staging_store import list_staging

    for i in range(3):
        write_to_layer(
            layer="system_mem",
            content=f"unauthorized attempt {i}",
            caller_id=f"unknown_caller_{i}",
            hermes_home=tmp_path,
        )

    entries = list_staging(hermes_home=tmp_path)
    assert len(entries) >= 3, "all denied writes must appear in staging"

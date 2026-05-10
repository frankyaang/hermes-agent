import json
from pathlib import Path
from agent.knowledge_audit import KnowledgeAuditLogger
from agent.knowledge_models import KnowledgeAuditEvent


def test_log_writes_jsonl(tmp_path):
    logger = KnowledgeAuditLogger(audit_dir=tmp_path)
    event = KnowledgeAuditEvent(
        event_id="test-id",
        timestamp="2026-05-10T00:00:00Z",
        user_id="feishu:ou_xxx",
        action="query",
        product_line_id="cleaning_robot",
        finance_flag=False,
        granted=True,
    )
    logger.log(event)

    files = list(tmp_path.rglob("audit.jsonl"))
    assert len(files) == 1
    line = json.loads(files[0].read_text().strip())
    assert line["user_id"] == "feishu:ou_xxx"
    assert line["action"] == "query"
    assert line["granted"] is True


def test_log_denied_event(tmp_path):
    logger = KnowledgeAuditLogger(audit_dir=tmp_path)
    event = KnowledgeAuditEvent(
        event_id="deny-id",
        timestamp="2026-05-10T00:00:00Z",
        user_id="feishu:ou_xxx",
        action="query",
        product_line_id="lawn_robot",
        finance_flag=False,
        granted=False,
        deny_reason="product_line_not_authorized",
    )
    logger.log(event)

    files = list(tmp_path.rglob("audit.jsonl"))
    line = json.loads(files[0].read_text().strip())
    assert line["granted"] is False
    assert line["deny_reason"] == "product_line_not_authorized"


def test_make_event_generates_uuid_and_timestamp(tmp_path):
    logger = KnowledgeAuditLogger(audit_dir=tmp_path)
    event = logger.make_event(
        user_id="u1",
        action="write",
        product_line_id="cleaning_robot",
        finance_flag=True,
        granted=True,
    )
    assert len(event.event_id) == 36  # UUID format
    assert "T" in event.timestamp     # ISO8601


def test_log_does_not_raise_on_dir_creation(tmp_path):
    deep = tmp_path / "a" / "b" / "c"
    logger = KnowledgeAuditLogger(audit_dir=deep)
    event = logger.make_event(
        user_id="u1", action="query",
        product_line_id="pl", finance_flag=False, granted=False,
    )
    logger.log(event)  # must not raise even if dir doesn't exist

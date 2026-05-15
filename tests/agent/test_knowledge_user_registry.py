import pytest
import yaml
from pathlib import Path
from agent.knowledge_user_registry import KnowledgeUserRegistry

SAMPLE = {
    "users": [
        {
            "user_id": "feishu:ou_xxx",
            "display_name": "张三",
            "platform": "feishu",
            "product_line_ids": ["cleaning_robot", "lawn_robot"],
            "default_product_line_id": "cleaning_robot",
            "finance_product_line_ids": ["cleaning_robot"],
            "role": "senior_business",
            "is_admin": False,
        },
        {
            "user_id": "feishu:ou_admin",
            "display_name": "管理员",
            "platform": "feishu",
            "product_line_ids": [],
            "default_product_line_id": "",
            "finance_product_line_ids": [],
            "role": "admin",
            "is_admin": True,
        },
    ]
}


@pytest.fixture
def reg_file(tmp_path) -> Path:
    p = tmp_path / "users.yaml"
    p.write_text(yaml.dump(SAMPLE))
    return p


def test_load_and_get_known_user(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_xxx")
    assert ctx is not None
    assert ctx.user_id == "feishu:ou_xxx"
    assert ctx.product_line_ids == ["cleaning_robot", "lawn_robot"]
    assert ctx.finance_product_line_ids == ["cleaning_robot"]
    assert ctx.is_admin is False


def test_get_unknown_user_returns_none(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    assert r.get_user("feishu:ou_unknown") is None


def test_missing_file_loads_empty(tmp_path):
    r = KnowledgeUserRegistry(registry_path=tmp_path / "no.yaml")
    r.load()  # must not raise
    assert r.get_user("anyone") is None


def test_validate_config_valid(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_xxx")
    assert r.validate_config(ctx) == []


def test_validate_config_bad_default(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_xxx")
    ctx.default_product_line_id = "nonexistent"
    errors = r.validate_config(ctx)
    assert any("default_product_line_id" in e for e in errors)


def test_validate_config_finance_not_subset(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_xxx")
    ctx.finance_product_line_ids = ["nonexistent"]
    errors = r.validate_config(ctx)
    assert any("finance_product_line_id" in e for e in errors)


def test_admin_user_loads_correctly(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_admin")
    assert ctx.is_admin is True


def test_conversation_access_defaults_to_default(reg_file):
    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_xxx")
    assert ctx.conversation_access == "default"


def test_conversation_access_loads_explicit_value(tmp_path):
    data = yaml.safe_load(yaml.dump(SAMPLE))
    data["users"][1]["conversation_access"] = "all_users"
    reg_file = tmp_path / "users.yaml"
    reg_file.write_text(yaml.dump(data))

    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_admin")
    assert ctx.conversation_access == "all_users"


def test_unknown_conversation_access_is_preserved_for_acl_to_ignore(tmp_path):
    data = yaml.safe_load(yaml.dump(SAMPLE))
    data["users"][1]["conversation_access"] = "unknown_scope"
    reg_file = tmp_path / "users.yaml"
    reg_file.write_text(yaml.dump(data))

    r = KnowledgeUserRegistry(registry_path=reg_file)
    r.load()
    ctx = r.get_user("feishu:ou_admin")
    assert ctx.conversation_access == "unknown_scope"

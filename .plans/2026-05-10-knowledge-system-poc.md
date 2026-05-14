# Knowledge System PoC Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 为 Hermes 新增一套独立的知识系统（KnowledgeProvider 抽象 + gbrain CLI 后端），强制产品线和财务数据权限隔离，读写都实现。

**Architecture:** Hermes Python 层新增 `KnowledgeManager`，持有 `KnowledgeUserContext` 和 `KnowledgeACLGuard`，在检索/写入前后做权限过滤；`GBrainCLIKnowledgeProvider` 通过子进程调用 `gbrain` CLI 实现存储和检索；用户注册表为 `~/.hermes/knowledge/users.yaml`。不修改任何 Hermes 核心文件（`run_agent.py`, `cli.py`, `gateway/run.py`），仅新建文件并在 `toolsets.py` 添加一个 toolset 条目。

**Tech Stack:** Python 3.11+, PyYAML（已在 Hermes venv）, gbrain CLI（`git clone + bun install + bun link`）, pytest（Hermes 测试套件）

---

## 文件结构

```
# 新建（纯逻辑，无 gbrain 依赖）
agent/knowledge_models.py          # 数据类：KnowledgeDoc, KnowledgeUserContext, AccessDecision, KnowledgeAuditEvent
agent/knowledge_acl.py             # KnowledgeACLGuard — 权限判断 + 结果过滤
agent/knowledge_user_registry.py   # YAML 用户注册表加载和校验
agent/knowledge_audit.py           # JSONL 审计日志写入
agent/knowledge_provider.py        # KnowledgeProvider ABC
agent/knowledge_manager.py         # KnowledgeManager — 编排以上所有模块

# 新建（gbrain 后端）
plugins/knowledge/__init__.py
plugins/knowledge/gbrain/__init__.py
plugins/knowledge/gbrain/provider.py   # GBrainCLIKnowledgeProvider

# 新建（工具注册）
tools/knowledge_tool.py            # knowledge_query + knowledge_write，注册到 registry

# 修改
toolsets.py                        # 新增 "knowledge" toolset 条目（_HERMES_CORE_TOOLS 不动）

# 测试（新建）
tests/agent/test_knowledge_acl.py
tests/agent/test_knowledge_user_registry.py
tests/agent/test_knowledge_manager.py
tests/agent/test_knowledge_audit.py

# 测试数据（不提交，本地初始化）
~/.hermes/knowledge/users.yaml
~/.hermes/knowledge/product_lines.yaml
```

---

## Task 1：数据模型

**Files:**
- Create: `agent/knowledge_models.py`

- [ ] **Step 1: 创建数据模型文件**

```python
# agent/knowledge_models.py
from __future__ import annotations
from dataclasses import dataclass, field


@dataclass
class KnowledgeUserContext:
    user_id: str
    product_line_ids: list[str]
    default_product_line_id: str
    finance_product_line_ids: list[str]
    role: str
    is_admin: bool


@dataclass
class KnowledgeDoc:
    slug: str
    title: str
    content: str
    product_line_id: str
    finance_flag: bool
    source_uri: str
    knowledge_type: str
    sensitivity_level: str
    confidence: str
    owner: str
    created_at: str
    updated_at: str
    updated_by: str
    snippet: str = ""


@dataclass
class AccessDecision:
    allowed: bool
    reason: str = ""

    @classmethod
    def allow(cls) -> "AccessDecision":
        return cls(allowed=True)

    @classmethod
    def deny(cls, reason: str) -> "AccessDecision":
        return cls(allowed=False, reason=reason)


@dataclass
class KnowledgeAuditEvent:
    event_id: str
    timestamp: str
    user_id: str
    action: str          # query / write / permission_denied
    product_line_id: str
    finance_flag: bool
    granted: bool
    deny_reason: str = ""
    knowledge_slugs: list[str] = field(default_factory=list)
    source_uris: list[str] = field(default_factory=list)
    query_text: str = ""
```

- [ ] **Step 2: 验证可导入（无依赖问题）**

```bash
cd /Users/frank/.hermes/hermes-agent-dev
source .venv/bin/activate
python -c "from agent.knowledge_models import KnowledgeDoc, KnowledgeUserContext, AccessDecision, KnowledgeAuditEvent; print('OK')"
```

Expected: `OK`

- [ ] **Step 3: Commit**

```bash
git add agent/knowledge_models.py
git commit -m "feat(knowledge): add data models (KnowledgeDoc, UserContext, AccessDecision, AuditEvent)"
```

---

## Task 2：ACL Guard

**Files:**
- Create: `agent/knowledge_acl.py`
- Create: `tests/agent/test_knowledge_acl.py`

- [ ] **Step 1: 写测试**

```python
# tests/agent/test_knowledge_acl.py
import pytest
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_models import KnowledgeUserContext, KnowledgeDoc
from datetime import datetime, timezone


def _ctx(**kw) -> KnowledgeUserContext:
    d = dict(user_id="u1", product_line_ids=["cleaning_robot"],
             default_product_line_id="cleaning_robot",
             finance_product_line_ids=[], role="user", is_admin=False)
    d.update(kw)
    return KnowledgeUserContext(**d)


def _doc(**kw) -> KnowledgeDoc:
    now = datetime.now(timezone.utc).isoformat()
    d = dict(slug="s", title="T", content="c", product_line_id="cleaning_robot",
             finance_flag=False, source_uri="feishu://doc/x",
             knowledge_type="product_spec", sensitivity_level="internal",
             confidence="unverified", owner="u1",
             created_at=now, updated_at=now, updated_by="u1")
    d.update(kw)
    return KnowledgeDoc(**d)


class TestCheckRead:
    def setup_method(self):
        self.g = KnowledgeACLGuard()

    def test_allow_authorized_product_line(self):
        assert self.g.check_read(_ctx(), "cleaning_robot", False).allowed

    def test_deny_unauthorized_product_line(self):
        r = self.g.check_read(_ctx(), "lawn_robot", False)
        assert not r.allowed
        assert r.reason == "product_line_not_authorized"

    def test_deny_finance_without_finance_permission(self):
        r = self.g.check_read(_ctx(finance_product_line_ids=[]), "cleaning_robot", True)
        assert not r.allowed
        assert r.reason == "finance_not_authorized"

    def test_allow_finance_with_finance_permission(self):
        r = self.g.check_read(_ctx(finance_product_line_ids=["cleaning_robot"]), "cleaning_robot", True)
        assert r.allowed

    def test_admin_bypasses_product_line(self):
        r = self.g.check_read(_ctx(product_line_ids=[], is_admin=True), "any", False)
        assert r.allowed

    def test_admin_bypasses_finance(self):
        r = self.g.check_read(_ctx(product_line_ids=[], is_admin=True), "any", True)
        assert r.allowed

    def test_deny_empty_user_id(self):
        r = self.g.check_read(_ctx(user_id=""), "cleaning_robot", False)
        assert not r.allowed
        assert r.reason == "user_identity_unknown"

    def test_deny_none_ctx(self):
        r = self.g.check_read(None, "cleaning_robot", False)
        assert not r.allowed


class TestCheckWrite:
    def setup_method(self):
        self.g = KnowledgeACLGuard()

    def test_allow_authorized(self):
        r = self.g.check_write(_ctx(), "cleaning_robot", False, "feishu://doc/x")
        assert r.allowed

    def test_deny_missing_source_uri(self):
        r = self.g.check_write(_ctx(), "cleaning_robot", False, "")
        assert not r.allowed
        assert r.reason == "source_uri_required"

    def test_deny_finance_without_finance_permission(self):
        r = self.g.check_write(_ctx(finance_product_line_ids=[]), "cleaning_robot", True, "feishu://doc/x")
        assert not r.allowed
        assert r.reason == "finance_write_not_authorized"

    def test_allow_finance_with_permission(self):
        r = self.g.check_write(_ctx(finance_product_line_ids=["cleaning_robot"]), "cleaning_robot", True, "feishu://doc/x")
        assert r.allowed

    def test_deny_unauthorized_product_line(self):
        r = self.g.check_write(_ctx(), "lawn_robot", False, "feishu://doc/x")
        assert not r.allowed


class TestFilterResults:
    def setup_method(self):
        self.g = KnowledgeACLGuard()

    def test_removes_unauthorized_product_line(self):
        ctx = _ctx(product_line_ids=["cleaning_robot"])
        docs = [_doc(product_line_id="cleaning_robot"), _doc(product_line_id="lawn_robot")]
        result = self.g.filter_results(ctx, docs)
        assert len(result) == 1
        assert result[0].product_line_id == "cleaning_robot"

    def test_removes_finance_without_permission(self):
        ctx = _ctx(finance_product_line_ids=[])
        docs = [_doc(finance_flag=False), _doc(finance_flag=True)]
        result = self.g.filter_results(ctx, docs)
        assert len(result) == 1
        assert not result[0].finance_flag

    def test_empty_input_returns_empty(self):
        assert self.g.filter_results(_ctx(), []) == []
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
cd /Users/frank/.hermes/hermes-agent-dev
scripts/run_tests.sh tests/agent/test_knowledge_acl.py -v 2>&1 | tail -5
```

Expected: `ERROR` 或 `ModuleNotFoundError: agent.knowledge_acl`

- [ ] **Step 3: 实现 ACL Guard**

```python
# agent/knowledge_acl.py
from __future__ import annotations
from agent.knowledge_models import KnowledgeUserContext, KnowledgeDoc, AccessDecision


class KnowledgeACLGuard:

    def check_read(
        self,
        ctx: KnowledgeUserContext | None,
        product_line_id: str,
        finance_flag: bool,
    ) -> AccessDecision:
        if not ctx or not ctx.user_id:
            return AccessDecision.deny("user_identity_unknown")
        if not ctx.is_admin:
            if product_line_id not in ctx.product_line_ids:
                return AccessDecision.deny("product_line_not_authorized")
        if finance_flag:
            if not ctx.is_admin and product_line_id not in ctx.finance_product_line_ids:
                return AccessDecision.deny("finance_not_authorized")
        return AccessDecision.allow()

    def check_write(
        self,
        ctx: KnowledgeUserContext | None,
        product_line_id: str,
        finance_flag: bool,
        source_uri: str,
    ) -> AccessDecision:
        if not source_uri:
            return AccessDecision.deny("source_uri_required")
        if not ctx or not ctx.user_id:
            return AccessDecision.deny("user_identity_unknown")
        if not ctx.is_admin:
            if product_line_id not in ctx.product_line_ids:
                return AccessDecision.deny("product_line_not_authorized")
        if finance_flag:
            if not ctx.is_admin and product_line_id not in ctx.finance_product_line_ids:
                return AccessDecision.deny("finance_write_not_authorized")
        return AccessDecision.allow()

    def filter_results(
        self,
        ctx: KnowledgeUserContext | None,
        results: list[KnowledgeDoc],
    ) -> list[KnowledgeDoc]:
        return [
            doc for doc in results
            if self.check_read(ctx, doc.product_line_id, doc.finance_flag).allowed
        ]
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_acl.py -v 2>&1 | tail -10
```

Expected: 全部 PASSED

- [ ] **Step 5: Commit**

```bash
git add agent/knowledge_acl.py tests/agent/test_knowledge_acl.py
git commit -m "feat(knowledge): add KnowledgeACLGuard with full permission matrix tests"
```

---

## Task 3：用户注册表

**Files:**
- Create: `agent/knowledge_user_registry.py`
- Create: `tests/agent/test_knowledge_user_registry.py`

- [ ] **Step 1: 写测试**

```python
# tests/agent/test_knowledge_user_registry.py
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
    r.load()   # must not raise
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
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_user_registry.py -v 2>&1 | tail -5
```

- [ ] **Step 3: 实现用户注册表**

```python
# agent/knowledge_user_registry.py
from __future__ import annotations
import logging
from pathlib import Path
from agent.knowledge_models import KnowledgeUserContext
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


class KnowledgeUserRegistry:
    def __init__(self, registry_path: Path | None = None):
        self._path = registry_path or (get_hermes_home() / "knowledge" / "users.yaml")
        self._cache: dict[str, KnowledgeUserContext] = {}

    def load(self) -> None:
        if not self._path.exists():
            logger.warning("knowledge user registry not found: %s", self._path)
            return
        import yaml
        with open(self._path) as f:
            data = yaml.safe_load(f) or {}
        self._cache = {}
        for user in data.get("users", []):
            ctx = KnowledgeUserContext(
                user_id=user["user_id"],
                product_line_ids=list(user.get("product_line_ids") or []),
                default_product_line_id=user.get("default_product_line_id") or "",
                finance_product_line_ids=list(user.get("finance_product_line_ids") or []),
                role=user.get("role", "user"),
                is_admin=bool(user.get("is_admin", False)),
            )
            self._cache[ctx.user_id] = ctx

    def get_user(self, user_id: str) -> KnowledgeUserContext | None:
        return self._cache.get(user_id)

    def validate_config(self, ctx: KnowledgeUserContext) -> list[str]:
        errors: list[str] = []
        if ctx.default_product_line_id and ctx.default_product_line_id not in ctx.product_line_ids:
            errors.append(
                f"default_product_line_id '{ctx.default_product_line_id}' not in product_line_ids"
            )
        for fpl in ctx.finance_product_line_ids:
            if fpl not in ctx.product_line_ids:
                errors.append(f"finance_product_line_id '{fpl}' not in product_line_ids")
        return errors
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_user_registry.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add agent/knowledge_user_registry.py tests/agent/test_knowledge_user_registry.py
git commit -m "feat(knowledge): add KnowledgeUserRegistry with YAML backend and config validation"
```

---

## Task 4：审计日志

**Files:**
- Create: `agent/knowledge_audit.py`
- Create: `tests/agent/test_knowledge_audit.py`

- [ ] **Step 1: 写测试**

```python
# tests/agent/test_knowledge_audit.py
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
    logger.log(event)   # must not raise even if dir doesn't exist
```

- [ ] **Step 2: 运行测试，确认失败**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_audit.py -v 2>&1 | tail -5
```

- [ ] **Step 3: 实现审计日志**

```python
# agent/knowledge_audit.py
from __future__ import annotations
import json
import logging
import uuid
from datetime import datetime, timezone
from pathlib import Path
from agent.knowledge_models import KnowledgeAuditEvent
from hermes_constants import get_hermes_home

logger = logging.getLogger(__name__)


class KnowledgeAuditLogger:
    def __init__(self, audit_dir: Path | None = None):
        self._base = audit_dir or (get_hermes_home() / "knowledge" / "audit")

    def log(self, event: KnowledgeAuditEvent) -> None:
        try:
            month = datetime.now(timezone.utc).strftime("%Y-%m")
            path = self._base / month / "audit.jsonl"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "a") as f:
                f.write(json.dumps({
                    "event_id": event.event_id,
                    "timestamp": event.timestamp,
                    "user_id": event.user_id,
                    "action": event.action,
                    "product_line_id": event.product_line_id,
                    "finance_flag": event.finance_flag,
                    "granted": event.granted,
                    "deny_reason": event.deny_reason,
                    "knowledge_slugs": event.knowledge_slugs,
                    "source_uris": event.source_uris,
                    "query_text": event.query_text,
                }) + "\n")
        except Exception as exc:
            logger.error("audit log write failed: %s", exc)

    def make_event(self, **kwargs) -> KnowledgeAuditEvent:
        return KnowledgeAuditEvent(
            event_id=str(uuid.uuid4()),
            timestamp=datetime.now(timezone.utc).isoformat(),
            **kwargs,
        )
```

- [ ] **Step 4: 运行测试，确认全部通过**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_audit.py -v 2>&1 | tail -10
```

- [ ] **Step 5: Commit**

```bash
git add agent/knowledge_audit.py tests/agent/test_knowledge_audit.py
git commit -m "feat(knowledge): add KnowledgeAuditLogger (JSONL, fail-safe)"
```

---

## Task 5：KnowledgeProvider ABC + KnowledgeManager

**Files:**
- Create: `agent/knowledge_provider.py`
- Create: `agent/knowledge_manager.py`
- Create: `tests/agent/test_knowledge_manager.py`

- [ ] **Step 1: 创建 KnowledgeProvider ABC**

```python
# agent/knowledge_provider.py
from __future__ import annotations
from abc import ABC, abstractmethod
from agent.knowledge_models import KnowledgeDoc


class KnowledgeProvider(ABC):

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def query(
        self,
        query: str,
        product_line_id: str,
        finance_flag: bool,
        limit: int = 10,
    ) -> list[KnowledgeDoc]: ...

    @abstractmethod
    def write(self, doc: KnowledgeDoc, actor_user_id: str) -> str:
        """写入知识条目，返回最终 slug。"""

    def shutdown(self) -> None:
        pass
```

- [ ] **Step 2: 写 KnowledgeManager 测试**

```python
# tests/agent/test_knowledge_manager.py
import pytest
from unittest.mock import MagicMock, patch
from agent.knowledge_manager import KnowledgeManager, PermissionDenied
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_models import KnowledgeUserContext, KnowledgeDoc
from datetime import datetime, timezone


def _ctx(**kw):
    d = dict(user_id="feishu:ou_xxx",
             product_line_ids=["cleaning_robot"],
             default_product_line_id="cleaning_robot",
             finance_product_line_ids=["cleaning_robot"],
             role="senior_business", is_admin=False)
    d.update(kw)
    return KnowledgeUserContext(**d)


def _doc(**kw):
    now = datetime.now(timezone.utc).isoformat()
    d = dict(slug="test-slug", title="T", content="c",
             product_line_id="cleaning_robot", finance_flag=False,
             source_uri="feishu://doc/x", knowledge_type="product_spec",
             sensitivity_level="internal", confidence="unverified",
             owner="feishu:ou_xxx", created_at=now, updated_at=now, updated_by="feishu:ou_xxx")
    d.update(kw)
    return KnowledgeDoc(**d)


def _manager(ctx=None, provider_docs=None, provider_slug="saved-slug"):
    ctx = ctx or _ctx()
    provider = MagicMock()
    provider.query.return_value = provider_docs or []
    provider.write.return_value = provider_slug
    audit = MagicMock()
    audit.make_event.return_value = MagicMock(
        knowledge_slugs=[], source_uris=[], granted=True, deny_reason="",
        action="", user_id="", product_line_id="", finance_flag=False,
        query_text="",
    )
    mgr = KnowledgeManager(ctx=ctx, provider=provider,
                           acl=KnowledgeACLGuard(), audit=audit)
    return mgr, provider, audit


# --- query tests ---

def test_query_authorized_returns_results():
    doc = _doc()
    mgr, provider, _ = _manager(provider_docs=[doc])
    results = mgr.query("test", "cleaning_robot")
    assert len(results) == 1
    provider.query.assert_called_once_with("test", "cleaning_robot", False)


def test_query_unauthorized_product_line_returns_empty():
    mgr, provider, _ = _manager()
    results = mgr.query("test", "lawn_robot")
    assert results == []
    provider.query.assert_not_called()


def test_query_finance_without_permission_returns_empty():
    mgr, provider, _ = _manager(ctx=_ctx(finance_product_line_ids=[]))
    results = mgr.query("revenue", "cleaning_robot", finance_ok=True)
    assert results == []
    provider.query.assert_not_called()


def test_query_finance_with_permission_calls_provider():
    doc = _doc(finance_flag=True)
    mgr, provider, _ = _manager(provider_docs=[doc])
    results = mgr.query("revenue", "cleaning_robot", finance_ok=True)
    assert len(results) == 1
    provider.query.assert_called_once_with("revenue", "cleaning_robot", True)


def test_query_filters_out_wrong_product_line_from_provider():
    """Provider 异常返回了其他产品线文档，KnowledgeManager 应二次过滤掉。"""
    bad_doc = _doc(product_line_id="lawn_robot")
    mgr, provider, _ = _manager(provider_docs=[bad_doc])
    results = mgr.query("test", "cleaning_robot")
    assert results == []


def test_query_provider_exception_returns_empty():
    mgr, provider, _ = _manager()
    provider.query.side_effect = RuntimeError("backend down")
    results = mgr.query("test", "cleaning_robot")
    assert results == []


def test_query_logs_audit_event():
    mgr, _, audit = _manager()
    mgr.query("test", "cleaning_robot")
    audit.log.assert_called_once()


# --- write tests ---

def test_write_authorized_calls_provider():
    mgr, provider, _ = _manager()
    slug = mgr.write(_doc())
    assert slug == "saved-slug"
    provider.write.assert_called_once()


def test_write_unauthorized_product_line_raises():
    mgr, provider, _ = _manager()
    with pytest.raises(PermissionDenied):
        mgr.write(_doc(product_line_id="lawn_robot"))
    provider.write.assert_not_called()


def test_write_finance_without_permission_raises():
    mgr, provider, _ = _manager(ctx=_ctx(finance_product_line_ids=[]))
    with pytest.raises(PermissionDenied):
        mgr.write(_doc(finance_flag=True))
    provider.write.assert_not_called()


def test_write_missing_source_uri_raises():
    mgr, provider, _ = _manager()
    with pytest.raises(PermissionDenied):
        mgr.write(_doc(source_uri=""))
    provider.write.assert_not_called()


def test_write_logs_audit_event():
    mgr, _, audit = _manager()
    mgr.write(_doc())
    audit.log.assert_called_once()
```

- [ ] **Step 3: 运行测试，确认失败**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_manager.py -v 2>&1 | tail -5
```

- [ ] **Step 4: 实现 KnowledgeManager**

```python
# agent/knowledge_manager.py
from __future__ import annotations
import logging
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from agent.knowledge_models import KnowledgeDoc, KnowledgeUserContext
from agent.knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)


class PermissionDenied(Exception):
    def __init__(self, reason: str):
        super().__init__(reason)
        self.reason = reason


class KnowledgeManager:

    def __init__(
        self,
        ctx: KnowledgeUserContext,
        provider: KnowledgeProvider,
        acl: KnowledgeACLGuard | None = None,
        audit: KnowledgeAuditLogger | None = None,
    ):
        self._ctx = ctx
        self._provider = provider
        self._acl = acl or KnowledgeACLGuard()
        self._audit = audit or KnowledgeAuditLogger()

    def query(
        self,
        query: str,
        product_line_id: str,
        finance_ok: bool = False,
    ) -> list[KnowledgeDoc]:
        decision = self._acl.check_read(self._ctx, product_line_id, finance_ok)
        event = self._audit.make_event(
            user_id=self._ctx.user_id,
            action="query",
            product_line_id=product_line_id,
            finance_flag=finance_ok,
            granted=decision.allowed,
            deny_reason=decision.reason,
            query_text=query,
        )
        if not decision.allowed:
            self._audit.log(event)
            return []
        try:
            raw = self._provider.query(query, product_line_id, finance_ok)
            results = self._acl.filter_results(self._ctx, raw)
            event.knowledge_slugs = [d.slug for d in results]
            event.source_uris = [d.source_uri for d in results if d.source_uri]
            self._audit.log(event)
            return results
        except Exception as exc:
            logger.error("knowledge query backend error: %s", exc)
            event.granted = False
            event.deny_reason = f"backend_error:{type(exc).__name__}"
            self._audit.log(event)
            return []

    def write(self, doc: KnowledgeDoc) -> str:
        decision = self._acl.check_write(
            self._ctx, doc.product_line_id, doc.finance_flag, doc.source_uri
        )
        event = self._audit.make_event(
            user_id=self._ctx.user_id,
            action="write",
            product_line_id=doc.product_line_id,
            finance_flag=doc.finance_flag,
            granted=decision.allowed,
            deny_reason=decision.reason,
            knowledge_slugs=[doc.slug],
            source_uris=[doc.source_uri] if doc.source_uri else [],
        )
        self._audit.log(event)
        if not decision.allowed:
            raise PermissionDenied(decision.reason)
        return self._provider.write(doc, self._ctx.user_id)
```

- [ ] **Step 5: 运行测试，确认全部通过**

```bash
scripts/run_tests.sh tests/agent/test_knowledge_manager.py -v 2>&1 | tail -10
```

- [ ] **Step 6: Commit**

```bash
git add agent/knowledge_provider.py agent/knowledge_manager.py \
        tests/agent/test_knowledge_manager.py
git commit -m "feat(knowledge): add KnowledgeProvider ABC and KnowledgeManager with ACL enforcement"
```

---

## Task 6：gbrain 安装与输出格式探查

> **注意：** 这个 Task 是探查性的，必须在 Task 7（gbrain provider 实现）之前完成。
> 实施者需要记录 `gbrain query` 和 `gbrain put` 的实际输出格式。

**Files:** 无新文件（探查任务）

- [ ] **Step 1: 安装 gbrain**

```bash
# 确认 bun 已安装
bun --version  # 若失败则：curl -fsSL https://bun.sh/install | bash

git clone https://github.com/garrytan/gbrain.git ~/gbrain
cd ~/gbrain
bun install
bun link   # 让 gbrain CLI 可全局调用
```

- [ ] **Step 2: 配置 API keys**

```bash
cd ~/gbrain
cp .env.example .env   # 若存在
# 编辑 .env，填写：
# OPENAI_API_KEY=sk-xxx    （必须，用于 embedding）
# ANTHROPIC_API_KEY=...    （可选）
```

- [ ] **Step 3: 初始化 brain（使用 PGLite 本地模式）**

```bash
cd ~/gbrain
gbrain init    # 按提示选择 PGLite engine（无需 Supabase）
gbrain health  # 确认输出包含 "pages: 0" 等统计信息
```

Expected output 示例：
```
Brain health: OK
Pages: 0  Chunks: 0  Links: 0
```

- [ ] **Step 4: 写入测试页面并探查 put 接口**

```bash
# 写入一个测试页面，观察接受什么格式的输入
cd ~/gbrain
echo "---
product_line_id: test_product_a
knowledge_type: product_spec
finance_flag: false
source_uri: test://local
---

这是测试产品线 A 的产品规格文档。" | gbrain put pl-test-product-a-general-spec-v1

# 确认写入成功
gbrain get pl-test-product-a-general-spec-v1
```

记录实际输出格式（slug 确认方式，成功/失败标志等）

- [ ] **Step 5: 探查 query 输出格式**

```bash
cd ~/gbrain
gbrain query "产品规格" 2>&1 | head -50
```

**关键记录项（填入下方，供 Task 7 使用）：**
- [ ] `gbrain query` 返回 JSON 还是纯文本？
- [ ] 若为 JSON：slug 字段名是什么？snippet/内容字段名是什么？frontmatter 如何表示？
- [ ] `gbrain put` 成功时的输出是什么？
- [ ] 是否有 `--json` 或 `--format=json` flag？

```bash
# 尝试 JSON flag
gbrain query "产品规格" --json 2>&1 | head -20
gbrain query "产品规格" --format=json 2>&1 | head -20
```

- [ ] **Step 6: 探查 MCP 工具列表**

```bash
# 在新 terminal 启动 gbrain MCP server
cd ~/gbrain
gbrain serve &
GBRAIN_PID=$!

# 用 mcp CLI 列出工具（若安装了 mcp CLI）
# 或通过 Python 探查：
cd /Users/frank/.hermes/hermes-agent-dev
source .venv/bin/activate
python - <<'EOF'
import asyncio
from mcp import ClientSession
from mcp.client.stdio import stdio_client, StdioServerParameters

async def list_tools():
    params = StdioServerParameters(command="gbrain", args=["serve"], cwd="/Users/frank/gbrain")
    async with stdio_client(params) as (r, w):
        async with ClientSession(r, w) as s:
            await s.initialize()
            tools = await s.list_tools()
            for t in tools.tools:
                print(f"  {t.name}: {t.description[:60]}")

asyncio.run(list_tools())
EOF

kill $GBRAIN_PID 2>/dev/null
```

记录实际 MCP 工具名称列表（供 Task 7 参考）

- [ ] **Step 7: 无需 commit（探查任务，结果记录在文档注释中）**

---

## Task 7：GBrainCLIKnowledgeProvider

> **前置条件：** Task 6 的探查必须完成，需知道 `gbrain query` 实际输出格式。

**Files:**
- Create: `plugins/knowledge/__init__.py`
- Create: `plugins/knowledge/gbrain/__init__.py`
- Create: `plugins/knowledge/gbrain/provider.py`

- [ ] **Step 1: 创建包文件**

```bash
touch /Users/frank/.hermes/hermes-agent-dev/plugins/knowledge/__init__.py
touch /Users/frank/.hermes/hermes-agent-dev/plugins/knowledge/gbrain/__init__.py
```

- [ ] **Step 2: 实现 Provider**

> 根据 Task 6 探查结果调整 `_parse_query_output` 方法。

```python
# plugins/knowledge/gbrain/provider.py
from __future__ import annotations
import json
import logging
import subprocess
from datetime import datetime, timezone
from pathlib import Path
from agent.knowledge_models import KnowledgeDoc
from agent.knowledge_provider import KnowledgeProvider

logger = logging.getLogger(__name__)


class GBrainCLIKnowledgeProvider(KnowledgeProvider):
    """gbrain CLI adapter（子进程调用）。

    slug 命名规范：pl-{product_line_id}-{finance|general}-{doc_slug}
    ACL 已由 KnowledgeManager 在调用前保证，provider 层只做存储/检索。
    """

    def __init__(self, gbrain_cwd: str | None = None):
        self._cwd = gbrain_cwd or str(Path.home() / "gbrain")

    @property
    def name(self) -> str:
        return "gbrain_cli"

    def is_available(self) -> bool:
        try:
            r = subprocess.run(
                ["gbrain", "health"],
                cwd=self._cwd,
                capture_output=True, text=True, timeout=10,
            )
            return r.returncode == 0
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    def _make_slug(self, product_line_id: str, finance_flag: bool, doc_slug: str) -> str:
        kind = "finance" if finance_flag else "general"
        return f"pl-{product_line_id}-{kind}-{doc_slug}"

    def _parse_query_output(self, output: str, product_line_id: str, finance_flag: bool) -> list[KnowledgeDoc]:
        """解析 gbrain query 输出。

        ⚠️  根据 Task 6 探查结果填写此方法。
        下方为 JSON 输出的假设实现，若 gbrain 输出格式不同则需要调整。
        """
        try:
            items = json.loads(output)
        except json.JSONDecodeError:
            # gbrain query 若为纯文本，此处需要改为文本解析
            logger.warning("gbrain query output is not JSON, got: %s", output[:200])
            return []

        docs: list[KnowledgeDoc] = []
        expected_prefix = f"pl-{product_line_id}-"
        for item in items:
            slug = item.get("slug", "")
            if not slug.startswith(expected_prefix):
                continue
            is_finance = f"pl-{product_line_id}-finance-" in slug
            if is_finance and not finance_flag:
                continue
            fm = item.get("frontmatter", {})
            docs.append(KnowledgeDoc(
                slug=slug,
                title=item.get("title", ""),
                content=item.get("compiled_truth", item.get("content", "")),
                snippet=item.get("snippet", "")[:500],
                product_line_id=fm.get("product_line_id", product_line_id),
                finance_flag=fm.get("finance_flag", is_finance),
                source_uri=fm.get("source_uri", ""),
                knowledge_type=fm.get("knowledge_type", "other"),
                sensitivity_level=fm.get("sensitivity_level", "internal"),
                confidence=fm.get("confidence", "unverified"),
                owner=fm.get("owner", ""),
                created_at=fm.get("created_at", ""),
                updated_at=fm.get("updated_at", ""),
                updated_by=fm.get("updated_by", ""),
            ))
        return docs

    def query(
        self,
        query: str,
        product_line_id: str,
        finance_flag: bool,
        limit: int = 10,
    ) -> list[KnowledgeDoc]:
        try:
            # 根据 Task 6 探查，若有 --json flag 则加上
            cmd = ["gbrain", "query", query, f"--limit={limit}"]
            r = subprocess.run(
                cmd, cwd=self._cwd,
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                logger.error("gbrain query failed (rc=%d): %s", r.returncode, r.stderr[:300])
                return []
            return self._parse_query_output(r.stdout, product_line_id, finance_flag)
        except subprocess.TimeoutExpired:
            logger.error("gbrain query timed out")
            return []
        except Exception as exc:
            logger.error("gbrain query exception: %s", exc)
            return []

    def write(self, doc: KnowledgeDoc, actor_user_id: str) -> str:
        slug = self._make_slug(doc.product_line_id, doc.finance_flag, doc.slug)
        now = datetime.now(timezone.utc).isoformat()
        page_content = (
            f"---\n"
            f"product_line_id: {doc.product_line_id}\n"
            f"knowledge_type: {doc.knowledge_type}\n"
            f"sensitivity_level: {doc.sensitivity_level}\n"
            f"finance_flag: {str(doc.finance_flag).lower()}\n"
            f"source_uri: {doc.source_uri}\n"
            f"owner: {doc.owner}\n"
            f"confidence: {doc.confidence}\n"
            f"created_at: {doc.created_at or now}\n"
            f"updated_at: {now}\n"
            f"updated_by: {actor_user_id}\n"
            f"---\n\n"
            f"# {doc.title}\n\n"
            f"{doc.content}\n"
        )
        try:
            r = subprocess.run(
                ["gbrain", "put", slug],
                input=page_content,
                cwd=self._cwd,
                capture_output=True, text=True, timeout=30,
            )
            if r.returncode != 0:
                raise RuntimeError(f"gbrain put failed: {r.stderr[:300]}")
            logger.info("gbrain put: wrote slug=%s", slug)
            return slug
        except subprocess.TimeoutExpired:
            raise RuntimeError("gbrain put timed out")
```

- [ ] **Step 3: 验证导入**

```bash
cd /Users/frank/.hermes/hermes-agent-dev
source .venv/bin/activate
python -c "from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider; print('OK')"
```

Expected: `OK`

- [ ] **Step 4: 手动验证 is_available**

```bash
python -c "
from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider
p = GBrainCLIKnowledgeProvider()
print('available:', p.is_available())
"
```

Expected: `available: True`（需要 gbrain 已安装）

- [ ] **Step 5: Commit**

```bash
git add plugins/knowledge/ 
git commit -m "feat(knowledge): add GBrainCLIKnowledgeProvider (subprocess adapter)"
```

---

## Task 8：knowledge_tool.py + toolsets 注册

**Files:**
- Create: `tools/knowledge_tool.py`
- Modify: `toolsets.py`（添加 knowledge toolset 条目）

- [ ] **Step 1: 创建 knowledge tool**

```python
# tools/knowledge_tool.py
from __future__ import annotations
import getpass
import json
import logging
import os
import re
from datetime import datetime, timezone
from tools.registry import registry
from gateway.session_context import get_session_env

logger = logging.getLogger(__name__)

# 每个 session_id 对应一个 KnowledgeManager 实例
_MANAGER_CACHE: dict[str, object] = {}


def _get_manager(session_id: str):
    """获取或创建当前会话的 KnowledgeManager。失败时返回 None（fail closed）。"""
    key = session_id or "cli_default"
    if key in _MANAGER_CACHE:
        return _MANAGER_CACHE[key]

    from agent.knowledge_user_registry import KnowledgeUserRegistry
    from agent.knowledge_manager import KnowledgeManager
    from agent.knowledge_acl import KnowledgeACLGuard
    from agent.knowledge_audit import KnowledgeAuditLogger
    from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider

    user_id = get_session_env("HERMES_SESSION_USER_ID", "")
    if not user_id:
        profile = os.getenv("HERMES_PROFILE", "default")
        user_id = f"cli:{getpass.getuser()}:{profile}"

    reg = KnowledgeUserRegistry()
    reg.load()
    ctx = reg.get_user(user_id)
    if ctx is None:
        logger.warning("knowledge: user_id=%r not in registry, access denied", user_id)
        return None

    errors = reg.validate_config(ctx)
    if errors:
        logger.error("knowledge: user config errors for %r: %s", user_id, errors)
        return None

    provider = GBrainCLIKnowledgeProvider()
    mgr = KnowledgeManager(
        ctx=ctx,
        provider=provider,
        acl=KnowledgeACLGuard(),
        audit=KnowledgeAuditLogger(),
    )
    _MANAGER_CACHE[key] = mgr
    return mgr


def _knowledge_query(query: str, product_line_id: str, finance: bool, task_id: str) -> str:
    mgr = _get_manager(task_id)
    if mgr is None:
        return json.dumps({"error": "access_denied", "reason": "user_not_registered_or_config_error"})

    if not product_line_id:
        product_line_id = mgr._ctx.default_product_line_id
    if not product_line_id:
        return json.dumps({"error": "no_product_line", "reason": "specify product_line_id or set default"})

    results = mgr.query(query, product_line_id, finance_ok=finance)
    return json.dumps({
        "count": len(results),
        "product_line_id": product_line_id,
        "finance_mode": finance,
        "results": [
            {
                "slug": d.slug,
                "title": d.title,
                "snippet": d.snippet or d.content[:300],
                "source_uri": d.source_uri,
                "confidence": d.confidence,
                "knowledge_type": d.knowledge_type,
            }
            for d in results
        ],
    })


def _knowledge_write(
    title: str,
    content: str,
    product_line_id: str,
    knowledge_type: str,
    source_uri: str,
    finance_flag: bool,
    sensitivity_level: str,
    confidence: str,
    doc_slug: str,
    task_id: str,
) -> str:
    from agent.knowledge_manager import PermissionDenied
    from agent.knowledge_models import KnowledgeDoc

    mgr = _get_manager(task_id)
    if mgr is None:
        return json.dumps({"error": "access_denied", "reason": "user_not_registered_or_config_error"})

    if not doc_slug:
        doc_slug = re.sub(r"[^a-z0-9]+", "-", title.lower())[:50].strip("-")

    now = datetime.now(timezone.utc).isoformat()
    doc = KnowledgeDoc(
        slug=doc_slug,
        title=title,
        content=content,
        product_line_id=product_line_id,
        finance_flag=finance_flag,
        source_uri=source_uri,
        knowledge_type=knowledge_type,
        sensitivity_level=sensitivity_level,
        confidence=confidence,
        owner=mgr._ctx.user_id,
        created_at=now,
        updated_at=now,
        updated_by=mgr._ctx.user_id,
    )
    try:
        slug = mgr.write(doc)
        return json.dumps({"success": True, "slug": slug, "product_line_id": product_line_id})
    except PermissionDenied as exc:
        return json.dumps({"error": "permission_denied", "reason": str(exc)})
    except Exception as exc:
        logger.error("knowledge write failed: %s", exc)
        return json.dumps({"error": "write_failed", "reason": str(exc)})


registry.register(
    name="knowledge_query",
    toolset="knowledge",
    schema={
        "name": "knowledge_query",
        "description": (
            "Query the business knowledge base. "
            "Returns docs from the user's authorized product line. "
            "Set finance=true only for financial data (requires finance permission). "
            "Never returns knowledge from unauthorized product lines."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "The search query"},
                "product_line_id": {
                    "type": "string",
                    "description": "Product line to search (e.g. 'cleaning_robot'). Defaults to user's default.",
                },
                "finance": {
                    "type": "boolean",
                    "description": "Set true to search financial knowledge (requires finance permission). Default false.",
                },
            },
            "required": ["query"],
        },
    },
    handler=lambda args, **kw: _knowledge_query(
        query=args["query"],
        product_line_id=args.get("product_line_id", ""),
        finance=bool(args.get("finance", False)),
        task_id=kw.get("task_id", ""),
    ),
)

registry.register(
    name="knowledge_write",
    toolset="knowledge",
    schema={
        "name": "knowledge_write",
        "description": (
            "Write a new knowledge entry to the business knowledge base. "
            "Requires business role or higher. source_uri is mandatory — "
            "no source, no write."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "title": {"type": "string"},
                "content": {"type": "string"},
                "product_line_id": {"type": "string"},
                "knowledge_type": {
                    "type": "string",
                    "enum": [
                        "product_spec", "org_info", "project_history",
                        "customer_feedback", "meeting_conclusion",
                        "financial_report", "financial_kpi", "financial_forecast",
                        "market_data", "compliance", "other",
                    ],
                },
                "source_uri": {
                    "type": "string",
                    "description": "Required: source document URI (e.g. feishu://doc/xxx, https://..., manual://)",
                },
                "finance_flag": {"type": "boolean", "description": "True if this is financial data. Default false."},
                "sensitivity_level": {
                    "type": "string",
                    "enum": ["public", "internal", "confidential", "secret"],
                    "description": "Default: internal",
                },
                "confidence": {
                    "type": "string",
                    "enum": ["draft", "unverified", "verified", "deprecated"],
                    "description": "Default: unverified",
                },
                "doc_slug": {
                    "type": "string",
                    "description": "Optional slug (auto-generated from title if omitted)",
                },
            },
            "required": ["title", "content", "product_line_id", "knowledge_type", "source_uri"],
        },
    },
    handler=lambda args, **kw: _knowledge_write(
        title=args["title"],
        content=args["content"],
        product_line_id=args["product_line_id"],
        knowledge_type=args["knowledge_type"],
        source_uri=args["source_uri"],
        finance_flag=bool(args.get("finance_flag", False)),
        sensitivity_level=args.get("sensitivity_level", "internal"),
        confidence=args.get("confidence", "unverified"),
        doc_slug=args.get("doc_slug", ""),
        task_id=kw.get("task_id", ""),
    ),
)
```

- [ ] **Step 2: 在 toolsets.py 添加 knowledge toolset**

在 `toolsets.py` 的 `TOOLSETS` 字典中（任意已有条目后面）添加：

```python
    "knowledge": {
        "description": "Business knowledge base — query and write product line knowledge with ACL enforcement",
        "tools": ["knowledge_query", "knowledge_write"],
        "includes": [],
    },
```

- [ ] **Step 3: 验证工具可注册**

```bash
cd /Users/frank/.hermes/hermes-agent-dev
source .venv/bin/activate
python -c "
import tools.knowledge_tool   # triggers registry.register()
from tools.registry import registry
schemas = registry.get_tool_schemas(['knowledge_query', 'knowledge_write'])
print('registered tools:', len(schemas))
for s in schemas:
    print(' -', s['name'])
"
```

Expected:
```
registered tools: 2
 - knowledge_query
 - knowledge_write
```

- [ ] **Step 4: Commit**

```bash
git add tools/knowledge_tool.py toolsets.py
git commit -m "feat(knowledge): register knowledge_query and knowledge_write tools"
```

---

## Task 9：测试数据初始化

> 本 Task 创建本地测试数据，不提交到 git（含敏感 user_id）。

- [ ] **Step 1: 创建用户注册表**

```bash
mkdir -p ~/.hermes/knowledge

# 获取当前系统用户名（用于 CLI user_id）
WHOAMI=$(whoami)
echo "CLI user_id 将是: cli:${WHOAMI}:default"

cat > ~/.hermes/knowledge/users.yaml << EOF
users:
  # 高级业务用户（有财务权限）
  - user_id: "cli:${WHOAMI}:default"
    display_name: "Frank (senior business)"
    platform: "cli"
    product_line_ids:
      - test_product_a
    default_product_line_id: "test_product_a"
    finance_product_line_ids:
      - test_product_a
    role: "senior_business"
    is_admin: false
    updated_at: "2026-05-10T00:00:00Z"
    updated_by: "admin"

  # 普通用户（无财务权限，用于验证隔离）
  - user_id: "feishu:ou_restricted_test"
    display_name: "Restricted User"
    platform: "feishu"
    product_line_ids:
      - test_product_a
    default_product_line_id: "test_product_a"
    finance_product_line_ids: []
    role: "user"
    is_admin: false
    updated_at: "2026-05-10T00:00:00Z"
    updated_by: "admin"

  # 管理员（跨产品线全访问）
  - user_id: "feishu:ou_admin_test"
    display_name: "Admin"
    platform: "feishu"
    product_line_ids: []
    default_product_line_id: ""
    finance_product_line_ids: []
    role: "admin"
    is_admin: true
    updated_at: "2026-05-10T00:00:00Z"
    updated_by: "admin"
EOF

cat ~/.hermes/knowledge/users.yaml
```

- [ ] **Step 2: 创建产品线配置**

```bash
cat > ~/.hermes/knowledge/product_lines.yaml << EOF
product_lines:
  - id: "test_product_a"
    display_name: "测试产品线 A"
    description: "用于 PoC 验证的测试产品线"
    created_at: "2026-05-10T00:00:00Z"

  - id: "test_product_b"
    display_name: "测试产品线 B"
    description: "用于隔离验证的第二个产品线（当前用户无权限）"
    created_at: "2026-05-10T00:00:00Z"
EOF
```

- [ ] **Step 3: 在 gbrain 中写入测试知识（普通 + 财务）**

```bash
cd ~/gbrain

# 普通知识：产品线 A 产品规格
echo "---
product_line_id: test_product_a
knowledge_type: product_spec
sensitivity_level: internal
finance_flag: false
source_uri: test://spec/v1
owner: admin
confidence: verified
created_at: 2026-05-10T00:00:00Z
updated_at: 2026-05-10T00:00:00Z
updated_by: admin
---

# 测试产品 A 规格 v1

这是测试产品线 A 的产品规格文档。
主要功能：自动清洁、智能导航、远程控制。
电池续航：120分钟。" | gbrain put pl-test-product-a-general-spec-v1

# 财务知识：产品线 A Q1 营收
echo "---
product_line_id: test_product_a
knowledge_type: financial_report
sensitivity_level: confidential
finance_flag: true
source_uri: test://finance/q1-2026
owner: admin
confidence: verified
created_at: 2026-05-10T00:00:00Z
updated_at: 2026-05-10T00:00:00Z
updated_by: admin
---

# 测试产品线 A Q1 2026 财务报告

Q1 营收：1000万。毛利率：45%。
（这是测试财务数据，仅用于权限验证。）" | gbrain put pl-test-product-a-finance-q1-2026

# 验证写入
gbrain get pl-test-product-a-general-spec-v1 | head -5
gbrain get pl-test-product-a-finance-q1-2026 | head -5
```

- [ ] **Step 4: 无需 Commit（本地数据）**

---

## Task 10：集成测试与权限隔离验证

- [ ] **Step 1: 验证普通知识检索（CLI 用户有权限）**

```bash
cd /Users/frank/.hermes/hermes-agent-dev
source .venv/bin/activate
python - << 'EOF'
from agent.knowledge_user_registry import KnowledgeUserRegistry
from agent.knowledge_manager import KnowledgeManager
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider
import getpass, os

user_id = f"cli:{getpass.getuser()}:default"
reg = KnowledgeUserRegistry()
reg.load()
ctx = reg.get_user(user_id)
assert ctx is not None, f"用户 {user_id} 不在注册表中"
print(f"用户加载成功: {ctx.user_id}, 产品线: {ctx.product_line_ids}")

mgr = KnowledgeManager(ctx=ctx, provider=GBrainCLIKnowledgeProvider(),
                        acl=KnowledgeACLGuard(), audit=KnowledgeAuditLogger())

results = mgr.query("产品规格", "test_product_a")
print(f"普通知识检索结果: {len(results)} 条")
for r in results:
    print(f"  - {r.slug}: {r.title}")
assert len(results) >= 1, "应该能查到产品规格文档"
print("✓ 普通知识检索通过")
EOF
```

- [ ] **Step 2: 验证财务知识检索（有权限）**

```bash
python - << 'EOF'
from agent.knowledge_user_registry import KnowledgeUserRegistry
from agent.knowledge_manager import KnowledgeManager
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider
import getpass

user_id = f"cli:{getpass.getuser()}:default"
reg = KnowledgeUserRegistry(); reg.load()
ctx = reg.get_user(user_id)
mgr = KnowledgeManager(ctx=ctx, provider=GBrainCLIKnowledgeProvider(),
                        acl=KnowledgeACLGuard(), audit=KnowledgeAuditLogger())

results = mgr.query("财务报告", "test_product_a", finance_ok=True)
print(f"财务知识检索结果: {len(results)} 条")
for r in results:
    print(f"  - {r.slug}: finance_flag={r.finance_flag}")
print("✓ 财务知识检索通过（高级业务用户有权限）")
EOF
```

- [ ] **Step 3: 验证财务隔离（普通用户无法访问财务）**

```bash
python - << 'EOF'
from agent.knowledge_user_registry import KnowledgeUserRegistry
from agent.knowledge_manager import KnowledgeManager
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider

# 模拟限制用户（finance_product_line_ids 为空）
reg = KnowledgeUserRegistry(); reg.load()
ctx = reg.get_user("feishu:ou_restricted_test")
assert ctx is not None
assert ctx.finance_product_line_ids == [], "测试用户不应有财务权限"

mgr = KnowledgeManager(ctx=ctx, provider=GBrainCLIKnowledgeProvider(),
                        acl=KnowledgeACLGuard(), audit=KnowledgeAuditLogger())

results = mgr.query("财务报告", "test_product_a", finance_ok=True)
assert results == [], f"普通用户不应看到财务数据，但得到: {results}"
print("✓ 财务隔离验证通过：普通用户查不到财务数据")
EOF
```

- [ ] **Step 4: 验证普通检索不返回财务内容**

```bash
python - << 'EOF'
from agent.knowledge_user_registry import KnowledgeUserRegistry
from agent.knowledge_manager import KnowledgeManager
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider

reg = KnowledgeUserRegistry(); reg.load()
ctx = reg.get_user("feishu:ou_restricted_test")

mgr = KnowledgeManager(ctx=ctx, provider=GBrainCLIKnowledgeProvider(),
                        acl=KnowledgeACLGuard(), audit=KnowledgeAuditLogger())

# 普通查询，即使 gbrain 返回了财务文档，也应被过滤
results = mgr.query("测试产品", "test_product_a", finance_ok=False)
finance_leaked = [r for r in results if r.finance_flag]
assert finance_leaked == [], f"财务内容不应出现在普通查询中: {finance_leaked}"
print(f"普通查询返回 {len(results)} 条，均为非财务内容 ✓")
EOF
```

- [ ] **Step 5: 验证跨产品线拒绝**

```bash
python - << 'EOF'
from agent.knowledge_user_registry import KnowledgeUserRegistry
from agent.knowledge_manager import KnowledgeManager
from agent.knowledge_acl import KnowledgeACLGuard
from agent.knowledge_audit import KnowledgeAuditLogger
from plugins.knowledge.gbrain.provider import GBrainCLIKnowledgeProvider
import getpass

reg = KnowledgeUserRegistry(); reg.load()
user_id = f"cli:{getpass.getuser()}:default"
ctx = reg.get_user(user_id)
# 此用户只有 test_product_a，没有 test_product_b

mgr = KnowledgeManager(ctx=ctx, provider=GBrainCLIKnowledgeProvider(),
                        acl=KnowledgeACLGuard(), audit=KnowledgeAuditLogger())

results = mgr.query("任意查询", "test_product_b")
assert results == [], "用户不应访问 test_product_b"
print("✓ 跨产品线隔离验证通过")
EOF
```

- [ ] **Step 6: 验证 knowledge_write 工具**

```bash
python - << 'EOF'
from tools.knowledge_tool import _knowledge_write
import getpass, json, os

os.environ["HERMES_SESSION_USER_ID"] = ""  # 触发 CLI user_id 推导

result = json.loads(_knowledge_write(
    title="测试写入文档",
    content="这是通过 knowledge_write 工具写入的测试文档。",
    product_line_id="test_product_a",
    knowledge_type="product_spec",
    source_uri="test://write/integration-test",
    finance_flag=False,
    sensitivity_level="internal",
    confidence="draft",
    doc_slug="integration-write-test",
    task_id="test-session",
))
print("写入结果:", result)
assert result.get("success") is True, f"写入失败: {result}"
print(f"✓ knowledge_write 通过，slug: {result['slug']}")
EOF
```

- [ ] **Step 7: 验证审计日志生成**

```bash
ls -la ~/.hermes/knowledge/audit/
cat ~/.hermes/knowledge/audit/*/audit.jsonl | python3 -c "
import json, sys
lines = [json.loads(l) for l in sys.stdin]
print(f'审计记录总数: {len(lines)}')
for l in lines[-5:]:
    print(f'  {l[\"action\"]:8} | granted={l[\"granted\"]} | pl={l[\"product_line_id\"]} | user={l[\"user_id\"]}')
"
```

- [ ] **Step 8: Commit**

```bash
git add .  # 只提交代码，不含 users.yaml（已在 .gitignore）
git commit -m "feat(knowledge): complete PoC integration — read/write + ACL isolation verified"
```

---

## 自检清单（Spec Coverage Review）

| 需求 | 实现任务 |
|------|----------|
| Memory 和 Knowledge 分离 | Task 1-5（独立模块，不触碰 memory_manager.py）|
| 产品线隔离（检索前过滤） | Task 2（KnowledgeACLGuard.check_read + filter_results）|
| 财务数据隔离（检索前过滤） | Task 2（finance_flag + finance_product_line_ids 检查）|
| 知识条目有来源、时间、责任人 | Task 1（KnowledgeDoc 字段）+ Task 7（frontmatter）|
| 用户权限模型 | Task 3（KnowledgeUserContext + users.yaml）|
| Feishu user_id 映射 | Task 9（users.yaml 中 feishu:ou_xxx 格式）|
| CLI user_id 映射 | Task 8（`_get_manager` 中 `cli:{user}:{profile}` 派生）|
| Fail closed（身份不可识别） | Task 5（manager 返回 [] 或 None）|
| Fail closed（source 缺失） | Task 2（check_write: source_uri_required）|
| Fail closed（backend 异常） | Task 5（query 的 except 块返回 []）|
| 审计日志（谁查了什么） | Task 4（KnowledgeAuditLogger）|
| 写入必须绑定 source_uri | Task 2 + Task 8（schema required + check_write）|
| 权限判断取交集 | Task 2（用户产品线权限 ∩ 知识条目产品线）|
| 不改 Hermes 核心文件 | Task 7-8（只改 toolsets.py，新建 tools/knowledge_tool.py）|
| profile-safe（get_hermes_home） | Task 3-4（KnowledgeUserRegistry + AuditLogger 均使用）|
| PoC 读写均实现 | Task 9-10（integration test 包含 write 验证）|

---

## 执行方式

计划已保存到 `.plans/2026-05-10-knowledge-system-poc.md`。

**两种执行方式：**

1. **Subagent 驱动（推荐）** — 每个 Task 派发独立 subagent，Task 间人工 review

2. **当前会话内联执行** — 使用 `executing-plans` skill，批量执行并设置检查点

**选哪种？**

# Hermes 知识系统集成方案

> 版本: 0.1-draft  
> 状态: 待确认，未实施  
> 作者: Claude Code（研究 + 设计阶段）  
> 日期: 2026-05-10

---

## 一、研究摘要（第一阶段结论）

### 1.1 Hermes 现状

| 模块 | 位置 | 关键发现 |
|------|------|----------|
| 记忆系统 | `agent/memory_provider.py` + `agent/memory_manager.py` | `MemoryProvider` ABC + `MemoryManager` 编排，已有一套完整的插件化内存框架 |
| 多用户记忆 | `agent_system/memory/user_mem/<user_id>/` | 目前为每用户独立目录（MEMORY.md / USER.md / memories/），无 ACL 层 |
| 用户身份 | `gateway/session_context.py` | `ContextVar` 方案：`HERMES_SESSION_USER_ID` 在每个异步任务中隔离，已传递 `user_id`、`platform`、`chat_id` 等 |
| 飞书身份 | `gateway/platforms/feishu.py` | 三级 ID：`open_id (ou_xxx)` App 级、`user_id (u_xxx)` 租户级、`union_id (on_xxx)` 开发者级；当前以 `union_id > open_id` 优先作会话键 |
| 工具注册 | `tools/registry.py` | 自动发现 + `registry.register()` 机制，所有工具返回 JSON 字符串 |
| ACP 权限 | `acp_adapter/permissions.py` | 仅为工具执行审批（allow/deny），与数据访问 ACL 无关 |
| 插件 | `plugins/memory/<name>/` | 每个插件实现 `MemoryProvider` ABC，一次只激活一个外部提供者 |

**结论**：Hermes 已有良好的插件框架和会话用户身份链路，但目前没有任何数据级 ACL 层。知识系统需要在 Hermes 内部构建权限守卫，不能依赖下层存储引擎来做。

### 1.2 gbrain 现状（关键约束：必须明确说明）

> **⚠️ gbrain v0 是单用户、本地运行系统，没有多用户支持、没有 ACL、没有命名空间隔离、没有 RLS。**

| 能力 | 现状 | 计划 |
|------|------|------|
| 多用户支持 | ❌ 不存在，GBRAIN_V0.md 明确写明 "single-user, local-only" | v1 roadmap |
| Row-Level Security | ❌ 不存在 | v1 roadmap（via Supabase RLS） |
| 命名空间 / 租户隔离 | ❌ 无，9 张表均无 tenant_id / product_line_id | v1 roadmap |
| 企业级 ACL | ❌ 不存在 | 未计划 |
| 混合检索 | ✅ vector + keyword + RRF fusion，P@5=49.1%，R@5=97.9% | 生产验证 |
| 知识图谱 | ✅ 有向图，typed relationships | 生产验证 |
| 存储引擎 | ✅ PGLiteEngine（嵌入式）/ PostgresEngine（Supabase）| 可插拔 |
| 接口 | ✅ CLI、MCP server（30+ 工具）、npm library | 生产验证 |
| 安装方式 | ✅ `git clone + bun install + bun link`（非 npm install -g） | 已验证 |

**推论**：不能把 gbrain 当成现成企业权限系统使用。所有 ACL 必须在 Hermes 层实施，gbrain 只作为检索/存储引擎使用。

---

## 二、目标（Goal）

构建一套与 Hermes 记忆系统**完全独立**的知识系统，满足：

1. 存储真实、可追溯、可审计的业务知识（产品线信息、财务数据、项目历史、客户反馈等）
2. 强制产品线隔离：不同产品线的知识在检索前过滤，不允许跨产品线泄露
3. 强制财务隔离：财务数据在检索前过滤，不由 LLM 提示词控制
4. 每条知识有来源、时间、责任人、置信度、更新历史
5. 权限不可判定时 fail closed
6. 被 Hermes Gateway、CLI、未来多平台场景复用

---

## 三、非目标（Non-Goals）

- **不替代记忆系统**：Memory 保留用户偏好、习惯、会话经验，Knowledge 存储业务知识
- **不把聊天记录自动进知识库**：知识写入必须有来源和责任人
- **不绕过权限**：LLM 永远不会看到未授权知识，包括摘要和引用片段
- **不盲目全量接入 gbrain**：只用 gbrain 的检索能力，ACL 在 Hermes 层
- **不依赖 gbrain 的企业 ACL**：gbrain v0 没有，v1 尚未发布

---

## 四、架构选项

### Option A：gbrain CLI/MCP Sidecar 集成

```
Hermes Agent
    ↓ tool call: knowledge_query(query, product_line_id, finance_allowed)
KnowledgeACLGuard（Hermes 层）
    ↓ 校验通过
gbrain MCP server（子进程/本地 HTTP）
    ↓
gbrain brain（PGLite / Supabase）
```

**优点**：最快上手；gbrain MCP 已有 30+ 工具；可用现有 `bun gbrain serve` 启动  
**缺点**：
- gbrain 没有 product_line 命名空间，需要在 slug 前缀或 tag 上做隔离（脆弱）
- 每个产品线需要独立的 gbrain 实例，或共享实例靠 slug 前缀分隔（风险高）
- gbrain MCP 暴露了全量工具给 LLM，ACL guard 如果绕过则泄露
- 适合 PoC，不适合生产多产品线

### Option B：Hermes 原生 KnowledgeProvider 抽象 + gbrain 作后端适配（推荐）

```
Hermes Agent
    ↓ tool call: knowledge_query / knowledge_write / ...
KnowledgeManager（Hermes 核心）
    ↓ [UserContext: user_id + product_line_ids + finance_product_line_ids]
KnowledgeACLGuard（权限守卫，在 Manager 内部）
    ↓ 检索前过滤 product_line_id + finance_flag
KnowledgeProvider ABC
    ├── GBrainKnowledgeProvider（gbrain 后端）
    │       ↓ slug namespace: pl:{product_line_id}:{doc_slug}
    │       gbrain PGLite / Supabase
    └── PostgresKnowledgeProvider（未来扩展）
```

**优点**：
- ACL 在 Hermes 层，不依赖 gbrain
- `KnowledgeProvider` ABC 与现有 `MemoryProvider` 对称，扩展成本低
- 工具暴露给 LLM 时已过滤，LLM 永远不会拿到未授权内容
- gbrain 作后端，复用其混合检索、知识图谱能力
- 支持未来替换后端（Postgres、Qdrant 等）

**缺点**：
- 需要新建 `KnowledgeProvider` ABC + `KnowledgeManager`（约 400-600 行）
- 需要用户注册表（`users.yaml`）

### Option C：独立 Postgres/Supabase 知识服务 + gbrain 只做索引层

```
Hermes → ACL Guard → Knowledge API（FastAPI）→ Postgres（产品线 + 财务数据）
                                              → gbrain（embedding + 检索）
```

**优点**：最企业级，RLS 可由 Postgres 原生实现，审计日志完整  
**缺点**：运维复杂度高，需要独立部署 FastAPI 服务；当前阶段过重

---

## 五、推荐方案

**推荐 Option B**，理由：

1. **符合 Hermes 现有架构范式**：`KnowledgeProvider` 与 `MemoryProvider` 对称，开发者熟悉
2. **ACL 在正确的层**：不依赖 gbrain（gbrain v0/v1 都不能作为权限边界）
3. **渐进可替换**：gbrain 只是第一个 backend，未来可换成 Postgres
4. **LLM 永远看不到未授权内容**：工具层过滤，不靠提示词
5. **PoC 可从 gbrain MCP sidecar 开始**，验证检索质量后再实现 Option B 的完整层

---

## 六、数据模型

### 6.1 用户访问模型（User Registry）

存储位置：`~/.hermes/knowledge/users.yaml`（或 Supabase `knowledge_users` 表）

```yaml
# 字段说明见下表
users:
  - user_id: "feishu:ou_xxx"          # platform:open_id 格式
    display_name: "张三"
    platform: "feishu"
    product_line_ids:                  # 可访问的产品线
      - cleaning_robot
      - lawn_robot
    default_product_line_id: "cleaning_robot"
    finance_product_line_ids:          # 可访问财务数据的产品线（子集）
      - cleaning_robot
    role: "senior_business"            # 见角色枚举
    is_admin: false
    updated_at: "2026-05-01T00:00:00Z"
    updated_by: "admin"
```

**角色枚举**：
- `user`：普通用户，只读授权产品线普通知识
- `business`：产品线业务人员，可写入普通知识
- `senior_business`：高级业务人员，可查看 + 写入财务知识（须在 finance_product_line_ids 中）
- `admin_local`：产品线管理员，管理该线知识
- `admin`：系统管理员，`is_admin=true` 时跨产品线全访问

**不变式**：
- `finance_product_line_ids ⊆ product_line_ids`，否则视为配置错误 fail closed
- `default_product_line_id ∈ product_line_ids`，否则 fail closed

### 6.2 产品线模型（Product Line Registry）

```yaml
# ~/.hermes/knowledge/product_lines.yaml
product_lines:
  - id: "cleaning_robot"
    display_name: "清洁机器人"
    description: "清洁机器人产品线"
    owners: ["feishu:ou_admin_xxx"]
    created_at: "2026-01-01T00:00:00Z"

  - id: "lawn_robot"
    display_name: "割草机器人"
    description: "割草机器人产品线"
    owners: ["feishu:ou_admin_yyy"]
    created_at: "2026-02-01T00:00:00Z"
```

### 6.3 知识文档模型（Knowledge Document）

每条知识条目的必须字段（对应 gbrain page frontmatter 扩展）：

```yaml
# 元数据（YAML frontmatter）
product_line_id: "cleaning_robot"      # 必须，产品线归属
knowledge_type: "product_spec"         # 见类型枚举
sensitivity_level: "internal"          # public / internal / confidential / secret
finance_flag: false                    # true = 财务数据，触发额外权限检查
source_uri: "feishu://doc/xxx"         # 来源 URI，必须存在才能写入
source_type: "feishu_doc"             # feishu_doc / meeting_transcript / manual / ...
owner: "feishu:ou_xxx"                # 负责人
created_at: "2026-05-01T00:00:00Z"
updated_at: "2026-05-01T00:00:00Z"
updated_by: "feishu:ou_xxx"
validity_window: "2026-12-31"          # 可选，知识过期时间
confidence: "verified"                 # draft / unverified / verified / deprecated
acl_roles: ["business", "senior_business", "admin"]  # 允许访问的最低角色

# slug 命名规范（gbrain 后端）
# 格式：pl:{product_line_id}:{finance|general}:{doc_slug}
# 示例：pl:cleaning_robot:general:product-spec-v3
#       pl:cleaning_robot:finance:q1-2026-revenue
```

**knowledge_type 枚举**：
`product_spec` / `org_info` / `project_history` / `customer_feedback` / `meeting_conclusion` / `financial_report` / `financial_kpi` / `financial_forecast` / `market_data` / `compliance` / `other`

### 6.4 财务知识模型

财务知识是普通知识的子集，额外要求：

```yaml
finance_flag: true                     # 必须为 true
knowledge_type: "financial_report"     # 或其他 financial_* 类型
sensitivity_level: "confidential"      # 最低 confidential
acl_roles: ["senior_business", "admin"]
finance_period: "2026-Q1"             # 财务周期
finance_scope: "product_line"         # product_line / company / segment
```

**写入要求**：
- 写入者的 `product_line_id` 必须在 `finance_product_line_ids` 中
- 写入时必须有来源 URI
- 审计日志必须记录写入行为

### 6.5 审计日志模型

```python
@dataclass
class KnowledgeAuditEvent:
    event_id: str              # UUID
    timestamp: str             # ISO8601
    user_id: str               # 操作者
    action: str                # query / write / delete / permission_denied
    product_line_id: str       # 涉及产品线
    finance_flag: bool         # 是否财务数据
    knowledge_ids: list[str]   # 涉及的知识条目 slug 列表
    source_ids: list[str]      # 返回的 source_uri 列表（查询时）
    query: str                 # 查询文本（查询时）
    granted: bool              # 是否有权限
    deny_reason: str           # 拒绝原因（权限不足时）
```

存储位置：`~/.hermes/knowledge/audit/YYYY-MM/audit.jsonl`（或 Supabase `knowledge_audit_log` 表）

---

## 七、权限模型

### 7.1 UserContext（权限判断的输入）

每个 Hermes 会话启动时，从用户注册表加载并注入：

```python
@dataclass
class KnowledgeUserContext:
    user_id: str
    product_line_ids: list[str]
    default_product_line_id: str
    finance_product_line_ids: list[str]
    role: str
    is_admin: bool
```

### 7.2 权限判断规则（KnowledgeACLGuard）

```python
class KnowledgeACLGuard:

    def check_read(
        self,
        ctx: KnowledgeUserContext,
        product_line_id: str,
        finance_flag: bool,
    ) -> AccessDecision:
        """
        检索前调用。返回 ALLOW / DENY + 原因。
        永远不抛异常，权限不确定时返回 DENY。
        """
        # 1. 用户身份必须可识别
        if not ctx or not ctx.user_id:
            return DENY("user_identity_unknown")

        # 2. 产品线权限
        if ctx.is_admin:
            pass  # admin 跳过产品线检查
        elif product_line_id not in ctx.product_line_ids:
            return DENY("product_line_not_authorized")

        # 3. 财务权限（产品线权限通过后再检查）
        if finance_flag:
            if ctx.is_admin:
                pass
            elif product_line_id not in ctx.finance_product_line_ids:
                return DENY("finance_not_authorized")

        return ALLOW()

    def check_write(
        self,
        ctx: KnowledgeUserContext,
        product_line_id: str,
        finance_flag: bool,
        source_uri: str,
    ) -> AccessDecision:
        """写入前校验。"""
        # 来源必须存在
        if not source_uri:
            return DENY("source_uri_required")

        # 产品线权限（同 check_read）
        if not ctx.is_admin and product_line_id not in ctx.product_line_ids:
            return DENY("product_line_not_authorized")

        # 财务写入额外要求
        if finance_flag:
            if not ctx.is_admin and product_line_id not in ctx.finance_product_line_ids:
                return DENY("finance_write_not_authorized")

        return ALLOW()

    def filter_results(
        self,
        ctx: KnowledgeUserContext,
        results: list[KnowledgeDoc],
    ) -> list[KnowledgeDoc]:
        """
        检索结果二次过滤（防止 backend 返回异常结果）。
        每条结果都再过一遍 check_read，不确定的直接丢弃。
        """
        allowed = []
        for doc in results:
            decision = self.check_read(ctx, doc.product_line_id, doc.finance_flag)
            if decision.allowed:
                allowed.append(doc)
        return allowed
```

### 7.3 默认产品线处理

```
会话开始
    ↓
用户没有指定产品线
    ↓
读取 user.default_product_line_id
    ↓
检查 default_product_line_id ∈ product_line_ids
    ↓ 否
    FAIL CLOSED：拒绝服务，记录审计，提示管理员修复配置
    ↓ 是
使用 default_product_line_id
```

### 7.4 跨产品线检索

```
默认：禁止跨产品线检索
    ↓
例外 1：is_admin = true → 允许
例外 2：用户显式指定了多个 product_line_ids，且请求明确要求对比 → 允许（需所有涉及产品线均在权限列表中）
跨产品线财务对比：还需所有涉及产品线均在 finance_product_line_ids 中
```

### 7.5 Fail Closed 场景清单

| 场景 | 行为 |
|------|------|
| 用户身份无法识别 | DENY，不服务，记录审计 |
| 用户注册表中找不到该 user_id | DENY，记录审计 |
| `default_product_line_id ∉ product_line_ids` | DENY，提示管理员修复配置 |
| `finance_product_line_ids ⊄ product_line_ids` | DENY，配置错误 |
| source_uri 为空时写入知识 | DENY，不写入 |
| 检索结果 product_line_id 与请求不符 | 丢弃该结果 |
| 权限判断抛出异常（如注册表文件损坏） | DENY，记录异常 |
| gbrain/后端抛出异常 | DENY，不返回部分结果 |

---

## 八、用户身份映射

### 8.1 Feishu

飞书平台现有三级 ID（来自 `gateway/platforms/feishu.py`）：

```
open_id (ou_xxx)  —— App 级，每个 App 不同
user_id (u_xxx)   —— 租户级，稳定
union_id (on_xxx) —— 开发者级，跨 App 稳定（最优选）
```

映射规则：
```python
def feishu_user_id(event) -> str:
    """
    优先用 union_id，退回 open_id。
    user_id (u_xxx) 需要额外权限，不作为主键。
    """
    uid = event.sender.sender_id
    if uid.union_id:
        return f"feishu:{uid.union_id}"   # on_xxx
    if uid.open_id:
        return f"feishu:{uid.open_id}"    # ou_xxx（fallback）
    raise IdentityError("cannot resolve feishu user_id")
```

在用户注册表中记录格式：`feishu:ou_xxx` 或 `feishu:on_xxx`

### 8.2 CLI 用户

```python
def cli_user_id() -> str:
    """CLI 用户从系统用户名 + HERMES_HOME profile 派生。"""
    import os, getpass
    profile = os.getenv("HERMES_PROFILE", "default")
    return f"cli:{getpass.getuser()}:{profile}"
```

CLI 用户在注册表中格式：`cli:frank:default`

### 8.3 其他平台扩展

| 平台 | 格式 | 来源字段 |
|------|------|----------|
| Telegram | `telegram:{user_id}` | `event.sender.id` |
| Discord | `discord:{user_id}` | `member.id` |
| Slack | `slack:{team_id}:{user_id}` | `event.user` |
| WeChat/WeCom | `wecom:{userid}` | `event.FromUserName` |
| DingTalk | `dingtalk:{staffId}` | `senderStaffId` |

---

## 九、KnowledgeProvider 抽象设计

### 9.1 KnowledgeProvider ABC

对标现有 `MemoryProvider` ABC，新建 `agent/knowledge_provider.py`：

```python
class KnowledgeProvider(ABC):
    """知识系统后端抽象。"""

    @property
    @abstractmethod
    def name(self) -> str: ...

    @abstractmethod
    def is_available(self) -> bool: ...

    @abstractmethod
    def initialize(self, hermes_home: str, **kwargs) -> None: ...

    @abstractmethod
    def query(
        self,
        query: str,
        product_line_id: str,
        finance_flag: bool,
        limit: int = 10,
    ) -> list[KnowledgeDoc]:
        """
        检索前已经过 ACL 过滤（由 KnowledgeManager 保证）。
        后端实现不需要做权限判断，只做检索。
        finance_flag=False 时 backend 必须过滤掉所有 finance_flag=True 的文档。
        """

    @abstractmethod
    def write(
        self,
        doc: KnowledgeDoc,
        actor_user_id: str,
    ) -> str:
        """写入知识条目，返回 slug/id。写入前 ACL 已由 KnowledgeManager 校验。"""

    @abstractmethod
    def get_tool_schemas(self) -> list[dict]: ...

    @abstractmethod
    def handle_tool_call(self, tool_name: str, args: dict, **kwargs) -> str: ...

    def shutdown(self) -> None: ...
```

### 9.2 KnowledgeManager

```python
class KnowledgeManager:
    """
    知识系统编排器。
    - 持有 UserContext
    - 持有 KnowledgeACLGuard
    - 代理到 KnowledgeProvider
    - 写入审计日志
    永远不把未授权内容返回给调用方。
    """

    def query(self, query: str, product_line_id: str, *, finance_ok: bool = False) -> list[KnowledgeDoc]:
        decision = self._acl.check_read(self._ctx, product_line_id, finance_ok)
        self._audit(action="query", product_line_id=product_line_id, finance_flag=finance_ok, granted=decision.allowed, query=query)
        if not decision.allowed:
            return []  # fail closed，不抛异常，不泄露原因给 LLM
        raw = self._provider.query(query, product_line_id, finance_ok)
        return self._acl.filter_results(self._ctx, raw)  # 二次过滤

    def write(self, doc: KnowledgeDoc) -> str:
        decision = self._acl.check_write(self._ctx, doc.product_line_id, doc.finance_flag, doc.source_uri)
        self._audit(action="write", ...)
        if not decision.allowed:
            raise PermissionDenied(decision.reason)
        return self._provider.write(doc, self._ctx.user_id)
```

### 9.3 GBrainKnowledgeProvider（第一个实现）

```python
class GBrainKnowledgeProvider(KnowledgeProvider):
    """
    通过 gbrain MCP 或 gbrain npm library 接入。
    所有 slug 带 product_line 前缀：
        pl:{product_line_id}:general:{slug}
        pl:{product_line_id}:finance:{slug}

    注意：
    - gbrain v0 没有 ACL，product_line 隔离靠前缀 + KnowledgeManager 的过滤
    - gbrain query 时用 tag filter：tag = pl:{product_line_id}
    - finance_flag=False 时额外排除 tag = finance
    """

    def query(self, query: str, product_line_id: str, finance_flag: bool, limit: int = 10):
        prefix = f"pl:{product_line_id}"
        # 通过 gbrain CLI 或 MCP：
        # gbrain query "<query>" --tag pl:cleaning_robot [--exclude-tag finance]
        ...
```

---

## 十、知识加载策略

### 10.1 会话启动时

```
用户发起会话（Gateway / CLI）
    ↓
gateway/session_context.py 设置 HERMES_SESSION_USER_ID
    ↓
KnowledgeManager.initialize(user_id=...) 从 users.yaml 加载 UserContext
    ↓
如果 user_id 不在注册表 → FAIL CLOSED（不启动知识系统，不影响记忆系统）
    ↓
默认加载 user.default_product_line_id 对应的知识上下文摘要（非全量）
    ↓
注入 system prompt block（只含权限范围内的产品线摘要，不含财务数据）
```

### 10.2 斜杠命令

```
/knowledge product-line list        → 列出用户有权限的产品线
/knowledge product-line set <id>    → 切换当前产品线（检查权限，fail closed）
/knowledge product-line info        → 显示当前产品线基本信息（无财务）
/knowledge search <query>           → 在当前产品线检索普通知识
/knowledge finance <query>          → 在当前产品线检索财务知识（需额外权限）
/knowledge write                    → 写入知识（需 business 以上角色）
/knowledge audit [--last 20]        → 查看本用户的操作审计记录
```

### 10.3 临时加载

- 用户可以临时切换到另一产品线（须在 `product_line_ids` 中）
- 临时加载不改变 `default_product_line_id`
- 每次切换记录审计日志

---

## 十一、检索策略

### 11.1 普通知识检索

```
knowledge_query(query, product_line_id="cleaning_robot")
    → ACL 检查: product_line_id ∈ user.product_line_ids
    → backend query: tag=pl:cleaning_robot, exclude finance
    → 返回结果: 不含任何 finance_flag=true 的文档
    → 结果格式: [{"title":..., "content":..., "source_uri":..., "confidence":...}]
```

### 11.2 财务知识检索

```
knowledge_query(query, product_line_id="cleaning_robot", finance=true)
    → ACL 检查1: product_line_id ∈ user.product_line_ids
    → ACL 检查2: product_line_id ∈ user.finance_product_line_ids
    → 两项都通过才执行 backend query
    → backend query: tag=pl:cleaning_robot, tag=finance
    → 结果中 source_uri 保留，但不自动插入 system prompt（需用户显式请求）
```

### 11.3 跨产品线检索

```
默认拒绝。只有：
    user.is_admin = true
    OR（多个 product_line_id 都在 user.product_line_ids 中，且请求明确包含跨产品线关键词）
才允许执行多产品线并行查询 + 结果聚合。
财务跨产品线还需所有涉及产品线在 finance_product_line_ids 中。
```

### 11.4 引用和摘要不得泄露未授权内容

- 检索结果的 summary 由 backend 返回，不由 LLM 重新生成（避免泄露）
- 若 LLM 尝试总结多个检索结果，KnowledgeManager 在注入前已过滤
- 工具返回值只包含已授权文档的 slug + snippet + source_uri，不返回原始全文

---

## 十二、写入策略

| 规则 | 说明 |
|------|------|
| source_uri 必须存在 | 无来源不得写入"真实知识" |
| product_line_id 必须在权限范围内 | 写入前校验 |
| finance 写入需要 finance_product_line_ids | 额外校验 |
| 写入自动记录 actor + timestamp + source | 不可绕过 |
| 写入后更新 audit log | 含 user_id、product_line_id、知识类型、source |
| 写入返回 slug | 可用于后续引用 |

---

## 十三、审计策略

所有以下操作写入审计日志（不可关闭）：

| 事件 | 字段 |
|------|------|
| 查询普通知识 | user_id, product_line_id, query, returned_slugs, timestamp |
| 查询财务知识 | 同上 + finance_flag=true |
| 权限拒绝 | user_id, attempted_product_line_id, deny_reason, timestamp |
| 写入知识 | user_id, product_line_id, slug, source_uri, finance_flag, timestamp |
| 修改知识 | 同上 + prev_version |
| 删除知识 | user_id, product_line_id, slug, reason, timestamp |
| 产品线切换 | user_id, from, to, timestamp |

审计日志存储：
- 短期：`~/.hermes/knowledge/audit/YYYY-MM/audit.jsonl`（每月一个文件）
- 长期：可选对接 Supabase `knowledge_audit_log` 表

---

## 十四、失败模式处理

```python
# 所有 KnowledgeManager 方法遵循以下模式：

def query(self, ...):
    try:
        # 1. 身份检查
        if not self._ctx:
            self._audit(action="query", granted=False, deny_reason="identity_unknown")
            return []  # fail closed

        # 2. ACL 检查
        decision = self._acl.check_read(...)
        if not decision.allowed:
            self._audit(...)
            return []  # fail closed，不抛异常

        # 3. backend 调用
        results = self._provider.query(...)

        # 4. 二次过滤（防御）
        return self._acl.filter_results(self._ctx, results)

    except Exception as e:
        logger.error("knowledge query failed: %s", e)
        self._audit(action="query", granted=False, deny_reason=f"backend_error:{type(e).__name__}")
        return []  # 任何异常都返回空，不返回部分结果
```

---

## 十五、验证计划

### 15.1 单元测试矩阵

| 测试场景 | 预期结果 |
|----------|----------|
| 用户 A 查询产品线 A | ALLOW，返回产品线 A 普通知识 |
| 用户 A 查询产品线 B（无权限） | DENY，返回空，审计记录 |
| 用户 A（普通业务）查询产品线 A 财务 | DENY，finance_not_authorized |
| 用户 A（高级业务 + finance_A）查询产品线 A 财务 | ALLOW |
| 管理员查询任意产品线 | ALLOW |
| 管理员跨产品线检索 | ALLOW |
| 普通用户发起跨产品线请求 | DENY |
| 财务跨产品线，但只有部分 finance 权限 | DENY |
| user_id 不在注册表中 | DENY，identity_not_found |
| default_product_line_id 配置错误 | DENY，config_error |
| source_uri 为空时写入 | DENY，source_uri_required |
| backend 抛出异常 | DENY，不返回部分结果 |
| 检索结果 summary 不含未授权内容 | 验证 filter_results 去除了所有越权文档 |

### 15.2 PoC 验证步骤

1. 搭建一个测试产品线 `test_product_a`
2. 创建两个测试用户（普通用户、高级业务）
3. 用 gbrain MCP sidecar 写入 3 条普通知识 + 1 条财务知识
4. 验证普通用户只能检索普通知识
5. 验证高级业务用户能检索财务知识
6. 验证用户 B 的 summary 和引用中不含产品线 A 的任何内容
7. 验证跨产品线请求被拒绝
8. 检查审计日志完整性

---

## 十六、PoC 最小实现建议

**第一步（只读检索 PoC）**：

1. 在 `~/.hermes/knowledge/users.yaml` 建立用户注册表（2 个测试用户）
2. 在 `~/.hermes/knowledge/product_lines.yaml` 建立产品线配置（1 个测试产品线）
3. 用 gbrain MCP sidecar 做只读检索（`gbrain serve` 本地启动）
4. 在 Hermes 外层实现 `KnowledgeACLGuard`（纯 Python，不改核心代码）
5. 新建 `tools/knowledge_query.py` 工具，在工具层做 ACL 过滤
6. 验证权限隔离后，再考虑写入能力

**第二步（写入 + 完整 KnowledgeProvider 层）**：
仅在方案确认 + PoC 通过后实施。

---

## 十七、重要约束（Implementation Constraints）

1. **财务数据不交给 LLM 后靠提示词过滤**：必须在工具层/检索层，LLM 永远不见未授权内容
2. **gbrain 不是权限边界**：gbrain v0 无 ACL，v1 RLS 尚未实施，ACL 必须在 Hermes 层
3. **安装方式**：使用 `git clone + bun install + bun link`，不使用 `npm install -g gbrain`
4. **用户注册表 = "谁能看什么"**，知识条目 = "这条知识属于什么和敏感等级"，权限判断 = 取交集
5. **所有写入必须有 source_uri**，无来源的 LLM 生成内容不得进入知识库
6. **不改动 Hermes 核心文件**（`run_agent.py`、`cli.py`、`gateway/run.py`），遵循插件模式
7. **profile-safe**：使用 `get_hermes_home()` 而非硬编码 `~/.hermes`
8. **prompt caching 安全**：知识系统初始化在会话开始时，不在对话中途重建 system prompt

---

## 十八、待确认事项（方案确认后方可实施）

在您确认以下决策前，不实施任何代码变更：

- [ ] **推荐 Option B 是否接受**？或选择其他选项？
- [ ] **用户注册表存储位置**：YAML 文件（`~/.hermes/knowledge/users.yaml`）还是 Supabase 表？
- [ ] **gbrain 接入方式**：MCP sidecar（`gbrain serve`），还是作为 npm library 直接导入 TypeScript？
- [ ] **PoC 范围**：先做只读检索验证，还是同步做写入？
- [ ] **财务数据隔离存储**：与普通知识同一 gbrain 实例（靠 tag 分隔），还是单独 gbrain 实例？
- [ ] **首个测试产品线**：用哪个产品线作为 PoC 测试对象？
- [ ] **审计日志短期存储**：JSONL 文件还是 Supabase？

---

*本文档为第二阶段输出，第三阶段代码实施需等待您的确认。*

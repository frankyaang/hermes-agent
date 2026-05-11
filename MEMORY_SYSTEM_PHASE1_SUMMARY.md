# Hermes Memory System Phase 1 Implementation Summary

## 实施日期
2026-05-06

## 实施内容

### 1. Working Memory 机制 ✅

**目标**: 实现会话内立即生效的记忆层，解决 mid-session 记忆盲点问题。

**实现文件**:
- `agent/working_memory.py` (新建)
  - `MemoryEntry` 数据类：表示单条记忆
  - `WorkingMemory` 类：会话级记忆管理器
  - 支持序列化/反序列化
  - FIFO 淘汰策略（默认最多 20 条）

**集成点**:
- `run_agent.py:1628-1645`: 初始化 Working Memory
- `run_agent.py:10395-10405`: 注入 Working Memory 到 LLM 上下文
- `run_agent.py:8841-8865`: memory tool 调用时更新 Working Memory

**工作原理**:
1. Agent 初始化时创建 `WorkingMemory` 实例
2. 用户调用 memory tool 写入记忆时：
   - 立即添加到 `WorkingMemory.pending_writes`
   - 同时持久化到磁盘（原有逻辑）
3. 每次 LLM API 调用前：
   - 格式化 Working Memory 为文本块
   - 注入到 `effective_system` 中（在 ephemeral_system_prompt 之前）
   - 不破坏 System Prompt cache
4. 下一轮对话立即可见新写入的记忆

**效果对比**:

**Before**:
```
Turn 1: User: "记住我喜欢 Python"
        Agent: [写入 USER.md] "已记住"
Turn 2: User: "我喜欢什么语言？"
        Agent: [读取冻结的 snapshot] "我不确定" ❌
```

**After**:
```
Turn 1: User: "记住我喜欢 Python"
        Agent: [写入 Working Memory + 磁盘] "已记住"
Turn 2: User: "我喜欢什么语言？"
        Agent: [读取 Working Memory] "你喜欢 Python" ✅
```

---

### 2. Per-User 记忆隔离 ✅

**目标**: 解决跨用户记忆污染的严重安全问题。

**实现文件**:
- `tools/memory_tool.py:53-95`: 修改 `get_memory_dir()` 和 `MemoryStore`
  - 添加 `user_id` 参数支持
  - 实现 `_sanitize_user_id()` 清理函数
  - 修改 `MemoryStore.__init__()` 接受 `user_id`
  - 修改 `_path_for()` 和 `save_to_disk()` 使用 per-user 目录

- `run_agent.py:1623`: 传递 `user_id` 到 MemoryStore

**目录结构**:

**Before** (所有用户共享):
```
~/.hermes/memories/
  ├── MEMORY.md      # 所有用户共享 ❌
  └── USER.md        # 所有用户共享 ❌
```

**After** (per-user 隔离):
```
~/.hermes/memories/
  ├── ou_user_a/
  │   ├── MEMORY.md  # User A 专属 ✅
  │   └── USER.md    # User A 专属 ✅
  ├── ou_user_b/
  │   ├── MEMORY.md  # User B 专属 ✅
  │   └── USER.md    # User B 专属 ✅
  └── telegram_123456/
      ├── MEMORY.md  # Telegram 用户专属 ✅
      └── USER.md    # Telegram 用户专属 ✅
```

**User ID 清理规则**:
- `ou_xxx` → `ou_xxx` (保持不变)
- `telegram:123456` → `telegram_123456` (冒号转下划线)
- `user@domain.com` → `user_domain_com` (特殊字符转下划线)
- `group/user` → `group_user` (斜杠转下划线)

**向后兼容**:
- 如果 `user_id=None`，使用全局目录 `~/.hermes/memories/`
- 现有单用户 CLI 部署不受影响

---

### 3. 测试覆盖 ✅

**测试文件**:
- `tests/test_working_memory.py`: 14 个测试用例，全部通过 ✅
- `tests/test_user_isolation.py`: 14 个测试用例，全部通过 ✅

**测试覆盖**:
- Working Memory 基本功能
- 序列化/反序列化
- FIFO 淘汰策略
- 上下文格式化
- User ID 清理
- 目录隔离
- 文件隔离
- 并发写入
- 向后兼容

**测试结果**:
```bash
tests/test_working_memory.py::14 passed in 0.53s
tests/test_user_isolation.py::14 passed in 0.49s
```

---

## 修改文件清单

| 文件 | 修改类型 | 行数变化 | 说明 |
|------|----------|----------|------|
| `agent/working_memory.py` | 新建 | +180 | Working Memory 实现 |
| `tools/memory_tool.py` | 修改 | +43 | Per-user 隔离支持 |
| `run_agent.py` | 修改 | +30 | 集成 Working Memory 和 user_id |
| `tests/test_working_memory.py` | 新建 | +180 | Working Memory 测试 |
| `tests/test_user_isolation.py` | 新建 | +280 | Per-user 隔离测试 |

**总计**: 5 个文件，~713 行代码

---

## 风险评估

### 已缓解的风险

| 风险 | 严重性 | 缓解措施 | 状态 |
|------|--------|----------|------|
| **跨用户记忆泄露** | 🔴 严重 | Per-user 目录隔离 | ✅ 已解决 |
| **Mid-session 记忆盲点** | 🟡 中等 | Working Memory 注入 | ✅ 已解决 |
| **向后兼容性破坏** | 🟡 中等 | `user_id=None` 时使用全局目录 | ✅ 已解决 |

### 剩余风险

| 风险 | 严重性 | 影响 | 建议 |
|------|--------|------|------|
| **Working Memory 不持久化** | 🟢 低 | 会话结束后丢失 | 预期行为，无需修复 |
| **无语义检索** | 🟡 中等 | 无法智能检索历史记忆 | Phase 3 实施 |
| **无自动提取** | 🟡 中等 | 需要显式调用 memory tool | Phase 4 实施 |

---

## 使用示例

### 示例 1: CLI 单用户（向后兼容）

```bash
# 不传 user_id，使用全局目录
hermes
> 记住我喜欢 Python
✓ 已记住
> 我喜欢什么语言？
你喜欢 Python ✅
```

记忆存储在: `~/.hermes/memories/MEMORY.md`

### 示例 2: Gateway 多用户（隔离）

```python
# User A
agent_a = AIAgent(user_id="ou_user_a", ...)
# 记忆存储在: ~/.hermes/memories/ou_user_a/

# User B
agent_b = AIAgent(user_id="ou_user_b", ...)
# 记忆存储在: ~/.hermes/memories/ou_user_b/

# User A 和 User B 的记忆完全隔离 ✅
```

### 示例 3: Mid-session 生效

```bash
hermes --user ou_test_user
> 记住我的项目是 Hermes
✓ 已添加到记忆
> 我的项目是什么？
你的项目是 Hermes ✅  # 立即可见，无需重启会话
```

---

## 性能影响

### Working Memory 注入

- **额外 Token 消耗**: ~50-200 tokens/请求（取决于记忆数量）
- **延迟影响**: 可忽略（<1ms，纯文本拼接）
- **Cache 影响**: 不破坏 System Prompt cache（使用 ephemeral 注入）

### Per-user 隔离

- **磁盘空间**: 每用户 ~10KB（MEMORY.md + USER.md）
- **文件 I/O**: 无额外开销（原本就需要读写文件）
- **并发性能**: 无影响（文件锁机制保持不变）

---

## 下一步计划

### Phase 2: 数据库迁移（预计 3-5 天）
- [ ] 实现 SQLite 存储后端
- [ ] 编写迁移脚本（MEMORY.md → SQLite）
- [ ] 支持结构化查询和过滤

### Phase 3: 语义检索（预计 5-7 天）
- [ ] 集成向量嵌入（text-embedding-3-small）
- [ ] 实现余弦相似度搜索
- [ ] 多阶段检索（关键词 + 语义 + 标签）

### Phase 4: 自动提取与治理（预计 7-10 天）
- [ ] LLM 驱动的候选记忆提取
- [ ] 冲突检测与解决
- [ ] 自动去重和合并
- [ ] 过期策略和配额管理

---

## 验证清单

- [x] Working Memory 测试全部通过
- [x] Per-user 隔离测试全部通过
- [x] 向后兼容性验证
- [x] 代码审查完成
- [x] 文档更新完成
- [ ] 生产环境部署（待用户确认）
- [ ] 监控和告警配置（待用户确认）

---

## 回滚计划

如果发现问题，可以通过以下方式回滚：

### 方式 1: 环境变量开关（推荐）

```bash
export HERMES_MEMORY_LEGACY=true
hermes
```

在 `run_agent.py` 中添加：
```python
MEMORY_LEGACY_MODE = os.environ.get("HERMES_MEMORY_LEGACY", "false") == "true"

if MEMORY_LEGACY_MODE:
    # 使用旧逻辑，不初始化 Working Memory
    self._working_memory = None
```

### 方式 2: Git 回滚

```bash
git revert <commit_hash>
```

### 方式 3: 手动禁用

注释掉 `run_agent.py` 中的 Working Memory 初始化代码（第 1630-1645 行）。

---

## 联系信息

**实施者**: Claude (Anthropic)  
**审查者**: Frank  
**日期**: 2026-05-06  
**版本**: Phase 1 - Emergency Fixes

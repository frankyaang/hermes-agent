# 深度养马专家（Builder Expert）

- English name: `builder_expert`
- 中文名：深度养马专家
- Type：interactive mode-activated meta-expert
- 触发：模式短语 "启动深度养马模式" → mode=on；"退出深度养马模式" → mode=off
- 适用 channel：所有已接入 channel（飞书 / Telegram / CLI）
- Private memory：`true`（创建过程的关键决策与失败模式沉淀到 `expert_mem/`）

---

## 1. 角色定义

本专家**仅在深度养马模式下激活**。激活后接管所有用户对话，**绕过 routes.json 的常规分发**，直到用户说"退出深度养马模式"。

它的产出物是 Hermes 自己的资产：新的 expert / skill / route 文件。

它不直接调用其他 skill — 它的"工具"是文件生成、JSON 校验、init_scheduler 试加载、飞书云文档读取等基础设施能力。

---

## 2. 9 阶段状态机

| Stage | 名称 | 主导方 | 退出条件 |
|---|---|---|---|
| 1 | ENTRY | runtime | 检测到入口短语 |
| 2 | INTAKE | builder_expert | 5 项必填字段已收齐 |
| 3 | ARCHITECT | builder_expert + 用户协商 | 用户确认拆分方案（含复用决策）|
| 4 | DRAFT | builder_expert | draft 文件全部生成完毕 |
| 5 | VALIDATE | runtime（自动） | JSON schema + 重名 + 依赖完整性通过 |
| 6 | DRY_RUN | runtime（自动）+ builder_expert（生成 mock 数据）| 试加载 + mock 跑通 |
| 7 | TRIAL_RUN | builder_expert + 用户提供数据 | 用户对真实输出满意 |
| 8 | COMMIT | builder_expert | 文件落正式位置 + routes.json patch + git add |
| 9 | NEXT_OR_EXIT | builder_expert | 用户决定继续或退出 |

每个 stage 切换时通过 briefing 节点向 channel 推送进度。

---

## 3. 各 Stage SOP

### Stage 1：ENTRY

由 runtime 完成，不在本专家职责内。runtime 检测入口短语 → 创建状态文件 `agent_system/temp/skill_creation_<user_id>_<channel_id>.json` → 进入 Stage 2。

退出短语优先级最高：任何 stage 听到退出短语都立即跳到清理逻辑。

### Stage 2：INTAKE（混合式提问）

**必填字段（一个一个引导式问，缺一不可）：**

1. **业务目标**：你想解决什么问题？（一句话）
2. **触发场景**：这个能力什么时候被调用？
   - 定时（cron）
   - 用户主动（聊天关键词 / 命令）
   - 事件驱动（某 pipeline 完成后 / 某 channel 收到特定消息）
3. **输入数据**：典型输入是什么类型？（VOC / 工单 / 评论 / 竞品数据 / 用户上传文件 / 多模态 / 已有数据源）
4. **输出产物**：期望产出什么？（报告 / 异常清单 / 看板结构 / 对话回复 / 写入数据库）
5. **运行流程**：一步一步描述这个能力的执行流程  ← 关键字段
   - 用户用自然语言描述："先 X，再 Y，最后 Z"
   - 这是 Stage 3 架构推断的核心依据

**选填字段（一次性列出，没有就跳过）：**
- 期望最长运行时间（默认 300 秒）
- 优先级 high / normal / low（默认 normal）
- 谁可以调用（owner / 全体 / 群白名单）
- 是否需要人工审核 user_gate（默认 false）
- 是否定时（如选定时，问 cron 表达式 / 周期描述）

收齐后进入 Stage 3。

### Stage 3：ARCHITECT（协商式 + Expert 复用）

**3a. 复用扫描（自动）：**

builder_expert 扫描 `agent_system/experts/` 下所有现有 expert：

- 读取每个 `expert.json` 的 `description` 和 `skills`
- 用语义相似度跟用户业务目标 / 运行流程做匹配
- 匹配度 ≥ 0.7 的 expert 进入候选清单

**3b. 提议（协商式）：**

情况一 — 候选清单非空：
> 我看到现有 expert 候选：
> - `ops_expert`（运营专家，覆盖运营报告 / Dashboard / 运营动作）
>
> 跟你的场景接近。你倾向：
> - [A] 复用 ops_expert（不新建 expert，只新建 skill）
> - [B] 新建一个独立 expert（场景差异大，需要独立决策视角）
> - [C] 复用 ops_expert + 把新 skill 注册到它的 skills[]（扩展现有 expert）

情况二 — 无强匹配：
> 现有 expert 都不太合适，建议新建。需要看现有 expert 列表请说"列出现有专家"。

**3c. 用户确认后构建方案：**

- 若复用：`route.supervision.primary_expert = 现有 expert id`，不生成新 expert 文件
- 若新建：流程同原 SOP，生成新 expert
- 若复用 + 扩展：生成新 skill，draft 一份带 patch 的现有 expert.json（仅修改 `skills[]`）

**3d. Skill / Route 拆分启发**（基于 INTAKE 第 5 项"运行流程"）：

| 业务特征 | 拆分动作 |
|---|---|
| 多决策视角（运营+技术+用户）| 多 expert |
| 单一职责执行 | 1 expert |
| 输入异构（多数据源）| 每源 1 skill |
| 串行业务流（A→B→C）| 1 route 多 step |
| 并行 + 汇总 | 多 skill + briefing 节点汇总 |
| 定时/事件驱动 | route 加 schedule trigger |
| 用户主动调用 | route 不加 schedule，依赖 user 触发 |

**默认最小化原则（强制写入 system prompt）：** 除非业务显式跨领域 / 输入显式异构，默认 **1 expert + 1 skill + 1 route**。LLM 倾向多拆装专业，需用此原则约束。

**3e. 输出方案 + 拆分理由：**

```
基于你的目标"X"和运行流程"先 A 再 B 最后 C"，建议：
- expert：复用 ops_expert（理由：单一运营视角）
- skills（2 个）：
  - skill_a：处理 A 类输入（理由：与现有 skill 输入类型不重叠）
  - skill_b：生成 C 类输出（理由：汇总步骤独立可复用）
- route：1 条 returns_radar_flow，串行 step，schedule=weekly

确认 / 调整 / 重新分析？
```

用户可用以下指令调整：
- "把 skill_a 和 skill_b 合并"
- "再拆一个 expert 处理 X"
- "去掉定时，改成用户触发"

### Stage 4：DRAFT

按 Stage 3 确认方案生成文件到 `_drafts/`：

```
agent_system/skills/_drafts/<skill_name>/
  ├── skill.json
  ├── SKILL.md
  ├── pipeline/<pipeline>.json
  └── skill_mem/         （空目录 + .gitkeep）

agent_system/experts/_drafts/<expert_name>/        （仅新建时）
  ├── expert.json
  ├── EXPERT.md
  └── expert_mem/        （空目录 + .gitkeep）

agent_system/scheduler/main_scheduler/routes.draft.json
  （合并候选 patch，记录 add / extend 两类操作）
```

字段模板**直接复用现有 skill / expert 的 JSON 结构**（参考 `briefing/` 和 `ops_expert/`）。

### Stage 5：VALIDATE（自动）

依次跑：

1. **JSON schema 校验**：必填字段齐全、type 合法
2. **重名检查**：`agent_system/skills/<name>` 或 `agent_system/experts/<name>` 不可已存在（除非显式 overwrite）
3. **依赖完整性**：route 引用的 expert / skill 必须能定位到 draft 或正式位置

任一失败 → 自动回 Stage 4 修正，最多重试 1 次；再失败 → 降级让用户手填问题字段。

### Stage 6：DRY_RUN（自动 + LLM 协助）

1. 调 `init_scheduler.py` 试加载 draft → 失败回 Stage 5
2. **builder_expert 自动生成 mock 数据**（基于 Stage 2 的 `input_type` 描述）→ 跑端到端一次
3. 检查输出物结构是否符合 Stage 2 描述的 `output_type`
4. 失败 → 回 Stage 3 让用户调整方案

### Stage 7：TRIAL_RUN（用户提供真实数据）

builder_expert 主动询问数据来源，按优先级：

| 优先级 | 数据源 | 接入方式 |
|---|---|---|
| 1 | 飞书云文档 | 用户贴 doc URL → 复用 Hermes 已有飞书 doc 读取 |
| 1 | 聊天贴文本 | 用户直接发 markdown / 表格 |
| 2 | Hermes 已接入数据源 | 用户指明（如"产线运营群最近 7 天"），调现有 channel reader |
| 2 | 用户上传文件 | 飞书附件 / CSV / JSON |

跑完后展示业务输出（briefing 风格），询问"是否符合预期？"
- 是 → Stage 8
- 否 → 回 Stage 3（带上失败原因，让 LLM 调整方案）

### Stage 8：COMMIT

1. `mv` draft → 正式位置
2. patch routes.json：先备份到 `routes.json.bak.<ts>` → 写入 → 给 user 看 diff
3. `git add` 所有新增文件 — **不自动 commit**
4. 提示用户："已 staged，请自行 review 并 commit"

### Stage 9：NEXT_OR_EXIT

询问"还要创建别的吗？"
- 是 → 回 Stage 2（保留之前 expert / skill 上下文，新创建可复用）
- 否或听到"退出深度养马模式" → 清状态文件 → 退出 mode

---

## 4. 失败 / 中断保护

- **跑偏检测**：用户连续 3 轮回答与当前 Stage 不相关 → 主动确认"我们继续创建还是暂停？"
- **中途换话题**：保留 state 文件不清，下次进入时识别到 stale state，问用户"继续上次的还是重新开始？"
- **退出兜底**：状态机任何阶段听到退出短语 → 立即跳到清理逻辑，询问"未完成的 draft 保留还是删除？"
- **JSON 解析失败**：LLM 生成的产物 schema 不合法 → 自动重试 1 次，仍失败则降级到表单式让用户手填

---

## 5. 经验沉淀

- 创建过程的关键决策（如"用户拒绝拆分多 expert 的建议"）写入 `expert_mem/decisions.jsonl`
- 反复出现的失败模式写入 `expert_mem/lessons.md`
- 下次 Stage 3 推断时，相关 lessons 作为反例注入 system prompt

---

## 6. 触发短语清单（与 expert.json 对齐）

入口短语：
- "启动深度养马模式"
- "进入深度养马模式"
- "开启深度养马模式"

退出短语：
- "退出深度养马模式"
- "结束深度养马模式"
- "关闭深度养马模式"

匹配规则：substring contains（不区分大小写），不做意图识别。

---

## 7. 状态文件 schema

文件位置：`agent_system/temp/skill_creation_<user_id>_<channel_id>.json`

```json
{
  "stage": "ARCHITECT",
  "mode_started_at": "ISO timestamp",
  "user_id": "ou_xxx",
  "channel_id": "oc_xxx",
  "intake": {
    "business_goal": "...",
    "scenario": "scheduled_weekly | user_triggered | event_driven",
    "input_type": "...",
    "output_type": "...",
    "pipeline_description": "先 X 再 Y 最后 Z",
    "max_runtime": 300,
    "priority": "normal",
    "user_gate": false
  },
  "architect_proposal": {
    "experts": [
      {"action": "reuse | create | extend", "name": "ops_expert", "rationale": "..."}
    ],
    "skills": [
      {"name": "...", "input": "...", "rationale": "..."}
    ],
    "routes": [
      {"pipeline_id": "...", "steps": [], "schedule": "weekly | null"}
    ],
    "user_confirmed": false
  },
  "drafts": {
    "expert_paths": [],
    "skill_paths": [],
    "routes_draft_path": "agent_system/scheduler/main_scheduler/routes.draft.json"
  },
  "validation": {"json_schema": null, "name_collision": null, "deps_complete": null},
  "dry_run": {"load_test": null, "mock_run": null},
  "trial_run": {"data_source": null, "data_ref": null, "output_summary": null},
  "history": [
    {"stage": "INTAKE", "completed_at": "...", "rounds": 6}
  ]
}
```

每个 stage 完成后写入 `history`，便于跑偏后恢复。

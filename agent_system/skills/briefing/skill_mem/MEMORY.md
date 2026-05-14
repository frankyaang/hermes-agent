# 过程汇报 私域经验

这里记录该 Skill 的示例经验、偏好和可复用执行线索。

---

## 2026-05-07: insight_flow GA/IPD/IPMS 流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **上游节点**: voc_insight（2 个专家并行：user_analyst + ops_expert）
- **输入**: 何春关于 GA 嵌入 IPD/IPMS 流程的管理层反馈

### briefing 模板经验
1. **结构模板**: 流程执行概览 → 上游节点摘要 → 执行质量评估 → 经验与异常 → 产出清单
2. **摘要粒度**: 每个上游节点需覆盖：执行方式、API 调用数、Token 消耗、核心任务、关键发现（≤5 条）、产出文件、数据来源
3. **质量评估维度**: 数据充分性、洞察深度、多专家协同、产出完整性、经验写入
4. **异常记录**: 明确标注无异常或异常详情，含 human review 触发情况

### 关键教训
- briefing 不做独立分析，而是**综合上游输出**生成结构化汇报
- 双专家场景下需体现协同互补关系，不简单叠加
- 动态覆盖（如 ops_expert 改用 ops_dashboard）需在汇报中明确说明
- 产出清单需含路径和大小，方便下游定位
- 2026-05-07T11:35:25.667875+00:00 `Run_insight_flow_20260507T112813` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-07T13:20:31.356263+00:00 `Run_dashboard_flow_20260507T131853` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-08T01:58:04.781787+00:00 `Run_insight_flow_20260508T014332` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-08T02:28:26.525952+00:00 `Run_insight_flow_20260508T021916` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=1; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-08: insight_flow 海外售后咨询数据分析流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **上游节点**: voc_insight（2 个专家并行：user_analyst + ops_expert）
- **输入**: 海外售后咨询数据分析需求（40,375 条记录，4 个维度）

### briefing 执行经验
1. **数据规模处理**: 成功汇报 40K+ 记录的分析结果，包含 32 国、462 机型、631 二级分类
2. **异常透明化**: ops_expert 遇到飞书客户端访问受限，在汇报中透明记录问题、根因和解决方案
3. **战略建议提炼**: 从 TOP 30 问题中提炼 P0 优先级战略建议（充电、污水回收、导航三大专项）
4. **技术亮点记录**: 记录 user_analyst 的环境回退策略、零外部依赖、自动分类逻辑等技术创新

### 关键教训
- **异常不等于失败**: ops_expert 虽受环境限制，但透明诊断和解决方案建议仍具价值
- **战略建议提炼**: briefing 可从上游洞察中提炼战略行动建议，增强汇报的决策支持价值
- **技术创新记录**: 记录上游专家的技术亮点，有助于经验传播和复用
- 2026-05-08T02:32:03.454587+00:00 `Run_insight_flow_20260508T021916` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-08T03:01:45.048384+00:00 `Run_insight_flow_20260508T025110` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-08: insight_flow 海外售后咨询数据分析流程汇报（第二次）

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **Run ID**: Run_insight_flow_20260508T053905
- **上游节点**: voc_insight（2 个专家并行：user_analyst + ops_expert）
- **输入**: 海外售后咨询数据分析需求（40,377 条记录，4 个维度）
- **执行时长**: 9分38秒（voc_insight节点总时长）

### briefing 执行经验
1. **大规模数据汇报**: 成功汇报 40K+ 记录的分析结果，包含 32 国、462 机型、631 二级分类
2. **双专家协同汇报**: 清晰呈现 user_analyst（数据分析）+ ops_expert（运营视角）的协同互补关系
3. **动态覆盖记录**: ops_expert 改用 ops_dashboard skill，在汇报中明确说明动态覆盖逻辑和原因
4. **环境适配透明化**: ops_expert 遇到飞书客户端访问受限，在汇报中透明记录问题、根因、解决方案（session_search fallback）
5. **战略建议提炼**: 从两位专家的洞察中提炼 P0/P1/P2 三级战略建议，增强汇报的决策支持价值
6. **质量评估多维度**: 数据充分性、洞察深度、多专家协同、产出完整性、经验写入 5 个维度评分
7. **产出清单详细化**: 每个文件含路径、大小、说明，方便下游定位

### 关键教训
- **异常不等于失败**: ops_expert 虽受环境限制，但透明诊断和 fallback 策略仍具价值，在汇报中应体现问题解决能力而非简单标记失败
- **战略建议提炼**: briefing 可从上游洞察中提炼战略行动建议（P0/P1/P2），增强汇报的决策支持价值
- **双专家协同呈现**: 不简单叠加两位专家的输出，而是呈现协同互补关系（数据分析 + 运营视角）
- **质量评估具体化**: 每个维度给出具体评分和改进空间，而非笼统的"完成"
- **下游建议**: briefing 可提供下游行动建议（立即行动、数据监控、经验复用），增强汇报的可操作性

### 产出文件
- **汇报文件**: `insight_flow_briefing_20260508T053905.md` (12.6KB)
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-08T05:48:43+00:00 `Run_insight_flow_20260508T053905` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-08T05:52:02.555276+00:00 `Run_insight_flow_20260508T053905` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-09: dashboard_flow 产品管理工具体系流程汇报

### 执行上下文
- **流程**: dashboard_flow（产品运营看板流程）
- **Run ID**: Run_dashboard_flow_20260509T003934
- **上游节点**: voc_insight（2 个专家并行：user_analyst + ops_expert）→ ops_dashboard（2 个专家并行：ops_expert + user_analyst）
- **输入**: 任务状态查询（"这个生成好了吗"）
- **执行时长**: 约 15 分钟（两个节点总时长）

### briefing 执行经验
1. **任务状态查询处理**: 成功汇报非典型输入（任务状态查询而非 VOC 数据），通过历史上下文恢复完整需求
2. **双节点四专家协同汇报**: 清晰呈现 voc_insight（user_analyst + ops_expert）→ ops_dashboard（ops_expert + user_analyst）的协同互补关系
3. **动态覆盖透明化**: 两个节点均发生专家技能动态覆盖，在汇报中明确说明覆盖逻辑和原因
4. **验证方法链记录**: search_files → ls 确认 → openpyxl 验证结构 → read_file 抽查质量，可复用至其他交付物验证场景
5. **历史上下文依赖**: 通过 session_search 恢复 2026-05-06/05-07 的完整需求，确保交付物符合原始期望
6. **用户洞察驱动改进**: 从用户需求理解角度识别潜在体验问题（学习成本、维护成本、工具分散），提供可操作的改进建议
7. **可复用性分析**: 提炼管理工具体系设计原则（8 字段格式、符号化标识、5 状态流转、4 步复盘法），可推广至其他团队

### 关键教训
- **验证优先于重新生成**: 当用户询问任务状态时，应先验证历史交付物是否存在，避免重复劳动
- **双专家协同模式**: 诊断 + 解决、技术验证 + 用户体验、完成报告 + 改进建议，确保全面性
- **下游建议分层**: 立即行动（用户确认、使用指导）、短期优化（降低学习成本、识别高频表）、长期改进（自动化同步、协作平台迁移）
- **统计表格化**: 使用表格呈现节点级统计、专家级统计、总计，提升可读性

### 产出文件
- **汇报文件**: `dashboard_flow_briefing_20260509.md` (18.4KB)
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-09T08:54:00+00:00 `Run_dashboard_flow_20260509T003934` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-09T00:57:47.151452+00:00 `Run_dashboard_flow_20260509T003934` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-10T15:20:24.283392+00:00 `Run_insight_flow_20260510T150231` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: insight_flow 用户画像报告转飞书云文档流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **Run ID**: Run_insight_flow_20260511T013522
- **上游节点**: voc_insight（2 个专家并行：user_analyst + ops_expert）
- **输入**: 杨子枫请求将用户画像与设置项交叉验证报告转为飞书云文档格式
- **源文件**: `user_persona_and_settings_crossvalidation_report.md` (36KB, 1033行)
- **执行时长**: 3分51秒（voc_insight节点总时长）

### briefing 执行经验
1. **格式转换任务汇报**: 不同于数据分析类任务，本次为交付物格式转换，汇报重点从"洞察发现"转向"技术执行质量"和"文档完整性"
2. **双技术策略对比**: user_analyst（纯文本 block_type:2，778 blocks / 20批次）vs ops_expert（混合 heading block_type:3/4/5/2，650 blocks / 15批次），体现可靠性 vs 可读性的 trade-off
3. **双租户备份**: ecoboost + nousresearch 两个飞书租户各产出一个完整文档，形成天然备份
4. **零异常执行**: 全流程无报错，两个专家均独立完成任务，无环境适配问题
5. **经验库全量更新**: 4 个经验库（2 skill + 2 expert）全部更新，长文档批量迁移技术路径进一步成熟

### 关键教训
- **格式转换任务的质量维度**: 数据充分性 → 内容完整性，洞察深度 → 格式保真度，产出完整性 → 双版本备份
- **双专家并行模式升级**: 从"诊断+解决"演进为"可靠性优先+体验优化"双轨，适用于高价值交付物场景
- **block type 选择指南**: 纯文本最可靠（适合核心交付），混合 heading 体验优（适合阅读场景），根据用途选择
- **汇报统计表格化**: 使用 API调用/Token/时长/Blocks/批次 五维表格对比双专家，提升信息密度

### 产出文件
- **汇报文件**: `insight_flow_briefing_20260511.md` (11.2KB)
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T01:40:13+00:00 `Run_insight_flow_20260511T013522` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T01:42:51.430140+00:00 `Run_insight_flow_20260511T013522` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: dashboard_flow 张欢重要沟通雷达流程汇报

### 执行上下文
- **流程**: dashboard_flow（产品运营看板流程）
- **Run ID**: Run_dashboard_flow_20260511T020027
- **上游节点**: voc_insight（2 个专家并行：user_analyst + ops_expert）→ ops_dashboard（2 个专家并行：ops_expert + user_analyst）
- **输入**: 张欢重要沟通雷达脚本数据包（权限阻断，零数据）
- **执行时长**: ~5 分 6 秒（两个节点总时长）

### briefing 执行经验
1. **零数据场景汇报**: 上游节点因 user_access_token 缺失全部输出零数据，briefing 重点从"洞察发现"转向"权限状态透明化"和"恢复路径"
2. **[SILENT] 策略记录**: ops_expert 在零数据场景下输出 [SILENT]，briefing 需明确说明该策略的意图（避免与 user_analyst 的结构化报告重复）
3. **双节点四专家协同**: voc_insight（user_analyst + ops_expert）→ ops_dashboard（ops_expert + user_analyst），两个节点均发生动态覆盖，汇报中需逐一标注
4. **质量评估适配**: 零数据场景下"数据充分性"和"洞察深度"无法评分，重点评估"多专家协同""产出完整性""经验写入"
5. **下游建议聚焦授权**: 所有建议围绕 OAuth 授权推进和 token 自动刷新机制，区别于有数据场景的分析类建议

### 关键教训
- **[SILENT] 不等于无产出**: ops_expert 的 [SILENT] 是有意识的策略选择，briefing 应记录其理由而非简单标记为空
- **零数据场景的结构复用**: ops_dashboard 生成的 8 段式模板可作为未来任何权限阻断雷达看板的标准输出
- **权限阻断的透明化**: 全链路统一声明私域边界（未使用 fallback），阻断原因和恢复路径清晰可追溯
- **统计表格化**: 使用 API调用/Token/时长 三维表格对比双专家，提升信息密度

### 产出文件
- **汇报文件**: `dashboard_flow_briefing_20260511.md` (6.2KB)
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T02:05:33+00:00 `Run_dashboard_flow_20260511T020027` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T02:08:11.835284+00:00 `Run_dashboard_flow_20260511T020027` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: insight_flow 用户选择“方法1”直接粘贴交付流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **Run ID**: Run_insight_flow_20260511T042925
- **上游节点**: voc_insight（user_analyst + ops_expert）
- **输入**: 用户回复“方法1”，选择将既有飞书格式报告直接复制粘贴到飞书文档
- **源文件**: `user_persona_report_feishu_format.md` (36,404 bytes, 1033 行)
- **执行时长**: 约 5分03秒（上游 voc_insight 节点墙钟）

### briefing 执行经验
1. **交付方式选择场景**: 当用户只回复“方法1/方法2”这类上一轮选项时，briefing 需先继承对话上下文，明确这是交付动作选择，而不是新需求。
2. **剪贴板类交付透明化**: 汇报中必须写明剪贴板已验证，同时提醒剪贴板易被后续复制覆盖，并给出重新 `pbcopy` 命令。
3. **状态汇报重点切换**: 此类任务的重点不是重新分析 VOC，而是说明“已完成什么、用户下一步做什么、如失败如何恢复”。
4. **动态覆盖照常记录**: 即便主任务是交付动作，仍需记录 `ops_expert → ops_dashboard` 的动态覆盖及其运营转译价值。
5. **文件校验信息固定化**: 产出清单应包含主报告、节点结果 MD/JSON、运营结论与 briefing 自身路径，并附 bytes/行数。

### 关键教训
- **不要重复分析**: 当上游报告已存在且用户选择导入方式时，优先闭环交付动作，避免重复生成报告。
- **剪贴板验证不是永久保证**: 只能证明验证时刻一致，最终用户粘贴前仍可能被覆盖；汇报中需保留源路径和恢复命令。
- **用户下一步必须显性化**: 此类过程汇报应把“请在飞书文档中按 ⌘V”放在核心结论中。

### 产出文件
- **汇报文件**: `insight_flow_briefing_20260511T043517_method1.md` (约 10.6KB)
- **结构化结果**: `insight_flow_briefing_20260511T043517_method1.json`
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T04:35:17+00:00 `Run_insight_flow_20260511T042925` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T04:39:00.484471+00:00 `Run_insight_flow_20260511T042925` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: dashboard_flow 张欢重要沟通雷达权限缺口流程汇报（14:00轮）

### 执行上下文
- **流程**: dashboard_flow（产品运营看板流程）
- **Run ID**: Run_dashboard_flow_20260511T060034
- **上游节点**: voc_insight → ops_dashboard
- **输入**: 张欢重要沟通雷达脚本数据包（窗口 2026-05-11 09:45:26 CST → 14:00:31 CST）
- **执行身份**: system 调用 briefing

### briefing 执行经验
1. **重复权限缺口场景**: 与 10:00 轮类似，本轮仍为张欢本人 user_access_token 缺失；briefing 应避免把 0 消息误写成“无新增事项”，而应明确“无法判定”。
2. **用户可见输出极简化**: 当脚本明确要求 missing_user_access_token 时，用户可见文本只保留一句授权缺口与下一步，不展开不可见来源长列表。
3. **OAuth 状态复核命令适配**: 当前 `~/.hermes/scripts/feishu_user_oauth.py status` 不支持 `--json` 参数；应使用 `status --person 张欢`，其输出已是 JSON 格式。
4. **过程汇报文件命名**: 同日多轮 cron 应使用带时间戳和场景后缀的文件名，避免覆盖早前 `dashboard_flow_briefing_20260511.md`。

### 产出文件
- **汇报文件**: `dashboard_flow_briefing_20260511T1409_radar_oauth_block.md` (6,056 bytes)
- **结构化结果**: `dashboard_flow_briefing_20260511T1409_radar_oauth_block.json` (3,294 bytes)
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T06:09:35+00:00 `Run_dashboard_flow_20260511T060034` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T06:12:44.807120+00:00 `Run_dashboard_flow_20260511T060034` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: dashboard_flow 张欢重要沟通雷达提醒暂停闭环流程汇报（14:30轮）

### 执行上下文
- **流程**: dashboard_flow（产品运营看板流程）
- **Run ID**: Run_dashboard_flow_20260511T061507
- **上游节点**: voc_insight → ops_dashboard
- **输入**: 用户回复“暂停重要沟通雷达的提醒”，指向 cron job `6bb4cce497f8`（张欢-重要沟通雷达）
- **执行身份**: system 调用 briefing

### briefing 执行经验
1. **暂停闭环场景汇报**: 当用户明确要求暂停某个提醒时，briefing 应聚焦“意图识别 → 调度状态 → 影响范围 → 恢复条件”，而不是重新展开业务数据分析。
2. **状态核验优先**: 对 cronjob 控制类流程，必须复核最新 `cronjob list`，明确目标任务 `state/enabled/paused_at`，并同时说明相邻任务是否未受影响。
3. **权限缺口不等于无事项**: 在张欢 UAT missing 时，继续保留“无法判断真实是否有重要沟通事项”的表述，避免把不可读误写成无事项。
4. **副作用透明化**: 本轮实际 pause 动作由上游 ops_expert 完成，briefing 本节点只做 verify-only 和文件/经验写入，需在审计记录中说明。
5. **用户可见输出短句化**: 面向用户的建议应直接说“已暂停；周报未同步暂停；授权恢复且确认后再恢复”，不输出 OAuth 链接或敏感路径。

### 产出文件
- **汇报文件**: `dashboard_flow_briefing_20260511T1430_radar_pause_confirmed.md` (9,201 bytes)
- **结构化结果**: `dashboard_flow_briefing_20260511T1430_radar_pause_confirmed.json` (6,699 bytes)
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T06:30:42+00:00 `Run_dashboard_flow_20260511T061507` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T06:35:03.164779+00:00 `Run_dashboard_flow_20260511T061507` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。


---

## 2026-05-11: insight_flow 家庭自主做饭双臂机器人 MVP 定义流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **Run ID**: Run_insight_flow_20260511T070846
- **上游节点**: voc_insight（user_analyst × voc_insight + ops_expert × ops_dashboard）
- **输入**: 从用户价值、用户体验验证标准和运营优先级角度，分析家庭自主做饭双臂机器人应如何定义 MVP。
- **执行身份**: system 调用 briefing
- **生成时间**: 2026-05-11 15:19:46 CST

### briefing 执行经验
1. **概念阶段非传统 VOC 汇报**: 当源材料是产品策略/定义问题而非评论数据时，briefing 必须显式写明数据边界，避免把策略推演写成样本统计结论。
2. **双专家互补呈现**: user_analyst 侧重用户价值、信任、安全门槛与双臂 ROI；ops_expert 侧重北极星指标、运营看板、试点门槛与路线图。汇报应综合为共同 MVP 定义，而不是简单拼接。
3. **机器人/硬件 MVP 汇报模板**: 推荐固定包含“一句话定义、范围/排除项、验证指标、安全门槛、运营优先级、待补数据、双臂/硬件差异化证据”。
4. **动态覆盖透明化**: ops_expert 改用 ops_dashboard 属合理覆盖，需在上游摘要和执行统计中明确说明。
5. **人工审核字段不一致处理**: 当 human_review_required=否/user_gate=false 但聚合字段出现 decision=missing/blocking=true 时，应记录为字段表征不一致并标注非阻塞，避免误报为用户门禁。

### 关键教训
- 做饭机器人 MVP 的 briefing 应强调“免看管成餐率”和“安全可信”优先于菜谱数量或拟人化动作。
- 对高风险家庭机器人场景，过程汇报需要单独列出安全 Go/No-Go 指标，不能只给业务结论。
- 输出建议应落到 PRD 边界、试点数据埋点和运营路线图，便于下游直接执行。

### 产出文件
- **汇报文件**: `insight_flow_briefing_20260511T151946_cooking_robot_mvp.md`
- **结构化结果**: `insight_flow_briefing_20260511T151946_cooking_robot_mvp.json`
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T15:19:46.847386+08:00 `Run_insight_flow_20260511T070846` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=briefing Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T07:20:20.369579+00:00 `Run_insight_flow_20260511T070846` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: insight_flow 洗衣 / 叠衣机器人场景需求流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **Run ID**: Run_insight_flow_20260511T083307
- **上游节点**: voc_insight（user_analyst × voc_insight + ops_expert × ops_dashboard）
- **输入**: 洗衣/叠衣机器人场景需求草案，包含语音/App/智能体触发、设备兼容问卷、脏衣收集、洗烘启动、衣物折叠与收纳需求。
- **执行身份**: system 调用 briefing
- **生成时间**: 2026-05-11 16:41:58 CST

### briefing 执行经验
1. **家务机器人闭环汇报模板**: 洗衣/叠衣类场景过程汇报应按“触发 → 设备兼容 → 收集 → 预检 → 投放洗烘 → 监控异常 → 取出 → 折叠 → 收纳/交付”呈现，避免只复述单点动作指标。
2. **单动作指标升级为闭环北极星**: 当上游同时给出入口指标和动作成功率时，briefing 应综合为“有效无人值守洗叠闭环率”，并保留原指标作为分层子指标。
3. **风险门禁显性化**: 家庭洗衣场景需单列误拾取、口袋异物、禁洗衣物、程序误选、夹衣漏水、潮湿误折叠等红线事件，不能只给平均成功率。
4. **动态覆盖透明化**: ops_expert 改用 ops_dashboard 属合理覆盖，需在上游摘要、执行统计与 audit_checks 中明确说明。
5. **概念阶段数据边界**: 源材料为需求草案时，不输出样本占比、Top15 fact pool 或 FRR/FFR 结论；需标注为产品定义型洞察。

### 关键教训
- 洗衣/叠衣机器人 MVP 应强调“少接管的洗叠闭环”和“可直接收纳的结果”，不是“会按洗衣机按钮”或“会折一件衣服”。
- 过程汇报需要把“当前缺失段”显性化：脏衣误拾取边界、分拣/异物预检、洗烘后取出转运、叠放/收纳完成态。
- 对家务机器人场景，下游建议应直接落到 PRD 边界、机型支持矩阵、状态机、红线审计、家庭试点埋点与折叠质量盲评。

### 产出文件
- **汇报文件**: `insight_flow_briefing_20260511T164158_laundry_folding.md`
- **结构化结果**: `insight_flow_briefing_20260511T164158_laundry_folding.json`
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T16:41:58+08:00 `Run_insight_flow_20260511T083307` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=briefing Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T08:47:53.203260+00:00 `Run_insight_flow_20260511T083307` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

---

## 2026-05-11: insight_flow 2代洗衣/叠衣需求字段矩阵流程汇报

### 执行上下文
- **流程**: insight_flow（用户洞察流程）
- **Run ID**: Run_insight_flow_20260511T090014
- **上游节点**: voc_insight（user_analyst × voc_insight + ops_expert × ops_dashboard）
- **输入**: 2代洗衣需求，包含语音/App/智能体触发、设备兼容问卷、指定区域脏衣收集、洗烘一体机投放启动、衣物折叠叠放与收纳交付。
- **执行身份**: system 调用 briefing
- **生成时间**: 2026-05-11 17:13:31 CST

### briefing 执行经验
1. **同类需求二次汇报避免简单复用**: 本轮与 16:41 洗衣/叠衣场景相似，但上游产物已更新为 17:01 字段矩阵版；briefing 需重新引用当前 run 的路径、统计、功能卡数量和新增信息。
2. **6卡 + 8卡综合呈现**: user_analyst 输出 6 张核心功能卡，ops_expert 输出 8 张运营功能卡；汇报应说明 ops_dashboard 额外强化“指定区域交付”和“家庭成员习惯智能体”，而不是把数量差异视为冲突。
3. **字段矩阵任务重点**: 当用户明确给出字段清单（用户价值、成本浮动、材料、规格、智能化、设计指标等）时，过程汇报要记录字段覆盖完整性，而非只输出产品洞察摘要。
4. **闭环北极星延续**: 洗衣/叠衣类家务机器人场景仍应把入口指标、投放成功率、折叠成功率统一升级为“有效无人值守洗叠闭环率”，并保留原指标作为分层子指标。
5. **人工审核字段不一致处理**: human_review_required=否/user_gate=false 但聚合字段出现 decision=missing/blocking=true 时，记录为字段表征不一致且非阻塞。

### 关键教训
- 对重复或相似的产品定义型输入，briefing 必须以当前 run 的上游产物为准，避免复用旧路径和旧统计。
- 过程汇报应突出“字段覆盖已完成”和“输出不等同于真实 VOC 样本统计”两条边界。
- 对家务机器人洗叠闭环，指定交付位置与低打扰智能体是从 demo 走向日常复用的重要补充。

### 产出文件
- **汇报文件**: `insight_flow_briefing_20260511T171331_laundry_gen2.md`
- **结构化结果**: `insight_flow_briefing_20260511T171331_laundry_gen2.json`
- **输出目录**: `/Users/frank/.hermes/hermes-agent-official/agent_system/skills/briefing/output/`

### 执行统计
- 2026-05-11T17:13:31+08:00 `Run_insight_flow_20260511T090014` Skill级经验: skill=briefing; calls=1; completed=1; average_quality=90.0; exceptions=0; 写入主体=briefing Skill；仅记录执行历史、异常统计和复盘反馈。
- 2026-05-11T09:20:05.270807+00:00 `Run_insight_flow_20260511T090014` Skill级经验: skill=briefing; calls=0; completed=0; average_quality=0.0; exceptions=0; 写入主体=对应 Skill；仅记录执行历史、异常统计和复盘反馈。

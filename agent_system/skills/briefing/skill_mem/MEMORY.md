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

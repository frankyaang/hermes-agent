# Robot Product Insight Asset Harness

Canonical ID：`robot-product-voc-survey-insight`
Formal Agent Name：`RobotInsight`
中文名：`机器人洞察`
用途：生成机器人产品多源洞察 bundle。

## 治理头

- 输入契约：标准化机器人分析参数与研究输入
- 输出契约：`artifact_manifest（产物清单）`
- human gate 策略：`allow_proxy_but_mark_directional_only`
- recovery 策略：bundle 校验失败时 fail closed；缺对象范围时优先在前门阻断。

## Role

`robot-product-voc-survey-insight` 是机器人产品洞察 bundle 执行资产。

它负责：

- 读取标准化机器人分析参数
- 生成主报告、专题稿、附录与任务板
- 回传 `artifact_manifest`
- 通过 bundle 质量闸门

## Output Rule

必须至少能索引到：

- `main_report`
- `presentation_main_report`
- `presentation_brief`
- `artifact_manifest`
- 关键专题或附录

## Validation Focus

- bundle 输入是否结构化
- `VOC-only / survey-only / portfolio_full` 示例是否齐备
- bundle manifest 是否可校验

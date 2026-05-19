# 议题提取

- English name: `issue_extractor`
- 中文名：议题提取
- Type: `extraction`
- Default pipeline: `weekly_flow`
- Private memory: `false`

从自由格式的周报原材料（飞书文档、群聊汇总、ops_dashboard 产出等）中，通过 LLM 提取结构化 `Issue` 列表。

## 关键约束

- **禁止推断缺失字段**：`recommended_option` 和 `owner_candidate` 只允许从原文明确提取，缺失时必须输出 `null`，不得猜测
- **schema 强验证**：LLM 输出必须经过 `Issue` schema 验证，验证失败时记录日志并跳过该议题
- **自由格式兼容**：不预设输入格式，支持任意结构文本

## 输入

任意格式的周报原材料文本（`str`）

## 输出

`List[Issue]`，序列化为 JSON，每条 Issue 包含：
- `title`、`background`、`source_ref`（必填）
- `recommended_option`（可为 `null`）
- `acceptance_criteria`（可为 `null`）
- `owner_candidate`（可为 `null`）
- `urgency`：`high` / `medium` / `low`
- `options`：备选方案列表

## Pipeline

作为 `weekly_flow` 的 step 1，输出传入 `decision_gate`（step 2）。

## Memory

无私域经验（`private_memory: false`），每次从原材料重新提取。

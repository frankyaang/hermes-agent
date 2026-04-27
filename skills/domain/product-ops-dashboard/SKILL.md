---
name: product-ops-dashboard
description: 面向机器人产品，尤其清洁机器人场景的产品运营 Dashboard 技能。Use when Codex needs to keep the current 看用户 method as the analysis backbone, produce a PM-style insight report around Top15, generational comparison, competitor substitution, and FRR/FFR risk correction, and then package the result into a product-operations dashboard deliverable, optionally bridging to voc-dashboard-html for HTML output.
---

# 产品运营Dashboard

Canonical ID：`product-ops-dashboard`
中文名：`产品运营Dashboard`
方法别名：`看用户`
用途：先用“看用户”方法把用户判断、竞争替代和质量风险读清楚，再把结果收成一个能拿来做产品运营沟通与复盘的 Dashboard 交付。

这不是一个更大的经营系统 skill。

当前范围固定为：

- 仍以 `Top15 -> 场景穿透 -> 代际 -> 竞争 -> FRR / FFR` 为事实底座
- 仍以“像一个会做产品的人在读用户”为最高文风约束
- 只是把最终交付从单一洞察 skill 升级成：
  - `主报告 / Markdown`
  - `Dashboard / HTML`

## 这个 skill 默认解决什么问题

它默认回答五件事：

- 用户为什么买
- 用户为什么持续认可
- 用户为什么失望
- 用户为什么改选
- 这些判断如何收成一个产品运营 Dashboard

也就是说：

- `看用户` 是方法层
- `产品运营Dashboard` 是交付层

## 默认工作流

固定按这条链执行：

1. 先确认这是不是“看用户 + Dashboard”问题，而不是单纯做标签统计或页面渲染。
2. 把评论、竞品、质量材料翻译成 `JudgmentUnit（用户判断单元）`。
3. 以 `Top15 fact pool（Top15 事实池）` 为事实底座。
4. 先生成 `表1：Top15 场景穿透与时间序列风险`。
5. 再生成：
   - `模块2：Top15 代际强对比`
   - `模块3：Top15 竞争强对比`
   - `表4A / 表4B：FRR / FFR 风险校正`
6. 先完成主报告：
   - `PM 总结提炼`
   - `用户还在用这两把尺子判断 X/T 系`
   - `PM 战略行动指南`
7. 再把主报告收成 Dashboard 信息架构：
   - 摘要卡
   - Top15 主表区
   - 代际区
   - 竞争区
   - 风险区
   - 行动区
8. 如果用户需要成品 Dashboard，默认桥接 `voc-dashboard-html` 生成 HTML。

绝不能反过来：

- 先画 Dashboard
- 再回头找证据凑内容

## 默认双交付

默认输出固定为两层：

### 1. 主报告

主报告继续沿用现有“看用户”骨架：

1. `执行摘要`
2. `X 系专场`
3. `T 系专场`
4. `服务链路专场`
5. `PM 战略行动指南`

其中 `X / T / 服务链路` 作为稳定观察对象保留，但当期任务定义动态生成。

### 2. Dashboard 成品

Dashboard 不是另一套分析。

它只是把主报告重组为更适合运营沟通与复盘的前台结构，至少包含：

- `摘要卡`
- `X / T 核心判断区`
- `Top15 穿透主表区`
- `代际对比区`
- `竞争对打区`
- `FRR / FFR 风险区`
- `行动建议区`

如果用户只要分析，不强制产出 Dashboard 成品。

如果用户明确要页面、HTML、仪表盘成品，默认调用：

- [voc-dashboard-html](../voc-dashboard-html/SKILL.md)

不要在本 skill 内重复实现 HTML renderer。

## 看用户方法层硬约束

以下方法约束全部保留：

- 逻辑上始终只有一份唯一报告，不分本品稿 / 竞品稿 / 质量稿。
- `Top15` 是事实池，也是前台主展示；模块1、模块2、模块3都必须完整展开。
- `表1` 与 `表1A` 合并为唯一穿透表。
- `FRR / FFR` 只做证据增强与风险校正，不抢主叙事。
- 竞争章节固定为：
  - `竞争总判断`
  - `每个竞品一张独立表`
  - `竞争综合收口`
- 竞品逐行表固定采用：
  - `同名指标优先`
  - `任务聚合作为补充`

## Dashboard 层硬约束

- Dashboard 不能改写主报告结论。
- Dashboard 不能压缩掉主报告里的关键表格字段。
- Dashboard 文案必须直接消费主报告里的 PM 语言，不能退回系统播报。
- Dashboard 成品优先复用现有渲染能力，不在本 skill 内重复造轮子。

## 文风规则

无论是报告还是 Dashboard，都必须：

- 像一个会做产品的人在读用户
- 讲用户会在什么瞬间更相信它
- 讲用户会在什么位置重新犹豫
- 讲竞品到底在抢哪条任务
- 讲问题为什么会把用户拉回返工、接管或流失

前台不解释：

- 系统有没有命中证据
- 系统为什么没找到 quote
- 标签层怎么映射

## 明确禁止的反模式

以下表达默认禁止出现：

- `暂无稳定 VOC 原声可对撞`
- `这一票`
- `投给`
- `改票`
- `还守得住`
- `暂时不会因为`
- `更容易被接住`
- `还要继续确认`
- `更像同一条任务的不同说法`
- `更轻松、更稳、更成熟`
- 任何“系统没找到 / 系统没有匹配到”式表达

## 什么时候只产报告，什么时候双交付

默认规则：

- 用户只问洞察、结论、竞品、FRR / FFR：
  - 只产主报告即可
- 用户明确提到：
  - `Dashboard`
  - `看板`
  - `仪表盘`
  - `HTML`
  - `可视化成品`
  - `AI Studio 风格页面`
  - 则产 `主报告 + Dashboard`

## 最小输入

至少需要：

- `category_name`
- `analysis_goal`
- `product_scope`
- `time_scope`
- `VOC` 数据

可选增强输入：

- `竞品数据`
- `FRR / FFR`
- `Top15 指标池`
- `现成主报告 Markdown`

## 推荐桥接顺序

当用户要 Dashboard 成品时：

1. 先完成 `product-ops-dashboard` 主报告
2. 再把主报告 Markdown 交给 `voc-dashboard-html`
3. 用 `voc-dashboard-html` 生成最终 HTML

不要先产 HTML 再反推报告。

## 与 autoresearch 的关系

当前 skill-lab / autoresearch 默认围绕：

- `product_ops_dashboard` source bundle
- `product_ops_dashboard` eval dataset

优化重点固定看：

- 是否仍保留“看用户”主线质量
- 是否能稳定输出 Dashboard 结构
- 是否能正确桥接 `voc-dashboard-html`
- 是否避免滑回“只是 VOC 报告 skill”

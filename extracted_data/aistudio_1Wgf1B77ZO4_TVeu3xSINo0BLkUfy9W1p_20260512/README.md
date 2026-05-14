# AI Studio 会话基础数据抽取说明

- 来源 URL：`https://aistudio.google.com/app/prompts/1Wgf1B77ZO4_TVeu3xSINo0BLkUfy9W1p`
- 页面标题：`Copy of Copy of Evaluate New Mid-Range Model`
- 页面显示 token：`41,760 tokens`
- 抽取日期：`2026-05-12`
- 抽取方式：Chrome 页面复制、AppleScript-JS DOM 抽取、滚动容器快照、截图留证。

## 主要产物

- `derived/merged_unique_snapshots.md`：52 个唯一原始文本快照合并，845848 bytes。
- `derived/thoughts_blocks_raw.md`：从唯一快照中抽出的 Thoughts/推理块，108850 bytes。
- `derived/unique_nonempty_lines.txt`：跨快照去重后的非空行，774 行。
- `attachments/attachment_manifest.md`：页面可见附件线索清单。
- `raw/`：96 个原始复制/DOM 文本文件。
- `screenshots/`：45 张截图证据。
- `logs/`：滚动、展开、hash、Chrome 开关状态等过程日志；已移除 Chrome Profile 偏好备份和缓存命中日志，避免混入无关隐私数据。

## 已识别附件线索

- `T系列用户分析`，页面显示 `4,953 tokens`，附近出现 `image.png`。
- `莎士比亚 量价渠分布 - 变更后`，页面显示 `5,808 tokens`。
- `莎士比亚 量价渠分布 - 变更前`，页面显示 `8,993 tokens`。

## 限制说明

- AI Studio 页面采用虚拟滚动，单次 `document.body.innerText` 不是全量 41,760 tokens，因此本次以多位置快照方式合并基础数据。
- 可见 DOM 中的 `Expand to view model thoughts` 已在滚动过程中尽量展开；仍可能存在未渲染到 DOM 的历史 Thoughts 未被页面提供。
- 页面复制和 DOM 未暴露附件下载 URL 或原始二进制文件，本次只保存附件名称、token 数和截图证据。
- 为启用 DOM 抽取，曾临时给 Chrome Profile 3 打开 `allow_javascript_apple_events`；抽取后已将 Profile 3 恢复为原始未设置状态。Default Profile 原本为开启状态，未改变其原始状态。

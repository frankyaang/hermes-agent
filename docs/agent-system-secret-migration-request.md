# Hermes Agent-System — Secret Migration Request

> **Status**: Awaiting user authorization  
> **Generated**: 2026-05-20  
> **Trigger**: `config_secret_detected=true` in production config snapshot  
> **Action required**: User must authorize migration; Claude Code will NOT migrate automatically.

---

## 检测结果

`scripts/snapshot_agent_system_production_config.py` 检测到以下配置路径包含明文 secret 材料。

**注意：以下只列路径，不列值。值被自动 redact。**

| 路径 | 类型 |
|------|------|
| `providers.xiamiapi.api_key` | Provider API key |
| `mcp_servers.feishu-docs.env.FEISHU_APP_SECRET` | Feishu App Secret |

> 值已被 `_REDACTED_` 替换。本文档中不存在任何 token、key 或 secret 的实际值。

---

## 建议迁移目标

| 检测路径 | 建议目标 |
|----------|---------|
| `providers.xiamiapi.api_key` | `/Users/frank/.hermes/.env` → `XIAMIAPI_API_KEY=<value>` |
| `mcp_servers.feishu-docs.env.FEISHU_APP_SECRET` | `/Users/frank/.hermes/.env` → `FEISHU_APP_SECRET=<value>` |

迁移后，配置文件中的对应字段应改为从环境变量读取，或设置为占位符 `${XIAMIAPI_API_KEY}` / `${FEISHU_APP_SECRET}`。

---

## 备份步骤

**在执行任何迁移之前**，请先备份当前配置：

```bash
# 定位当前 hermes config 文件（通常在 ~/.hermes/ 下）
ls ~/.hermes/*.yaml ~/.hermes/*.json ~/.hermes/config* 2>/dev/null

# 备份（选择实际存在的路径）
cp ~/.hermes/config.yaml ~/.hermes/config.yaml.bak.$(date +%Y%m%d)
# 或
cp ~/.hermes/config.json ~/.hermes/config.json.bak.$(date +%Y%m%d)
```

---

## 迁移步骤

> **前提**: 用户已确认授权。Claude Code 不会自动执行以下命令。

### Step 1 — 创建或更新 `.env`

```bash
# 编辑（不要 echo 值到终端）
nano /Users/frank/.hermes/.env
```

在 `.env` 中添加：

```
XIAMIAPI_API_KEY=<从当前 config 复制，不要留在命令行>
FEISHU_APP_SECRET=<从当前 config 复制，不要留在命令行>
```

确保 `.env` 权限只允许当前用户读取：

```bash
chmod 600 /Users/frank/.hermes/.env
```

### Step 2 — 更新配置文件

将配置中的明文值替换为环境变量引用。具体语法取决于 Hermes config loader；常见形式：

```yaml
providers:
  xiamiapi:
    api_key: ${XIAMIAPI_API_KEY}

mcp_servers:
  feishu-docs:
    env:
      FEISHU_APP_SECRET: ${FEISHU_APP_SECRET}
```

### Step 3 — 确认配置 loader 支持 env var 展开

```bash
python3 -c "
from agent_system.production_config_snapshot import build_production_config_snapshot
from pathlib import Path
snap = build_production_config_snapshot(
    hermes_home=Path('/Users/frank/.hermes'),
    repo_root=Path('/Users/frank/.hermes/hermes-agent-official'),
)
print('config_secret_detected:', snap.get('config_secret_detected'))
"
```

如果输出 `config_secret_detected: False`，迁移成功。

---

## 回滚步骤

如果迁移后出现 auth 失败：

```bash
# 恢复备份（使用 Step 0 创建的备份文件名）
cp ~/.hermes/config.yaml.bak.20260520 ~/.hermes/config.yaml

# 重新生成 snapshot 确认恢复
python3 scripts/snapshot_agent_system_production_config.py
```

---

## 迁移后验证命令

```bash
# 1. 重新生成 config snapshot
python3 scripts/snapshot_agent_system_production_config.py

# 2. 确认 secret 不再被检测到
python3 scripts/snapshot_agent_system_production_config.py | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  print('config_secret_detected:', d.get('config_secret_detected'))"

# 3. 运行完整 status check
python3 scripts/agent_system_status.py --hermes-home /Users/frank/.hermes

# 4. 确认 config_secret_detected 不再出现在 missing_evidence
python3 scripts/preflight_agent_system_upgrade.py --hermes-home /Users/frank/.hermes
```

---

## 重要说明

- 本文档**不包含任何 secret 值**，只列路径
- 迁移前**必须获得用户明确授权**
- 迁移后如果 Hermes 连接 xiamiapi 或 Feishu 失败，**立即回滚**
- `.env` 文件**不得提交到 git**（已在 `.gitignore` 中）
- 完成迁移后，在 `upgrade_allowed` 判断中 `config_secret_detected` 这个 blocker 会消除

---

## 当前 blocker 状态

```bash
python3 scripts/agent_system_blockers.py --hermes-home /Users/frank/.hermes | \
  python3 -c "import sys,json; d=json.load(sys.stdin); \
  [print(b['blocker_code'], ':', b['current_evidence']) \
   for b in d['blockers'] if b['blocker_code']=='config_secret_detected']"
```

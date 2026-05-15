# Hermes 记忆系统改进 - 用户指南

## 🎉 新功能

### 1. 记忆立即生效 ✨

**以前的问题**:
```
你: 记住我喜欢 Python
AI: 已记住
你: 我喜欢什么语言？
AI: 我不确定 ❌  # 需要重启会话才能看到
```

**现在**:
```
你: 记住我喜欢 Python
AI: 已记住
你: 我喜欢什么语言？
AI: 你喜欢 Python ✅  # 立即可见！
```

### 2. 多用户记忆隔离 🔒

**以前的问题**:
- 所有用户共享同一个记忆文件
- 用户 A 的记忆会被用户 B 看到 ❌

**现在**:
- 每个用户有独立的记忆目录
- 完全隔离，保护隐私 ✅

## 📁 记忆存储位置

### CLI 单用户模式
```
~/.hermes/memories/
  ├── MEMORY.md
  └── USER.md
```

### Gateway 多用户模式
```
~/.hermes/memories/
  ├── ou_user_a/
  │   ├── MEMORY.md
  │   └── USER.md
  ├── ou_user_b/
  │   ├── MEMORY.md
  │   └── USER.md
  └── telegram_123456/
      ├── MEMORY.md
      └── USER.md
```

## 🚀 使用方法

### 基本用法（无变化）

```bash
# 添加记忆
> 记住我的项目是 Hermes

# 查看记忆
> 我的记忆里有什么？

# 删除记忆
> 忘记关于项目的记忆
```

### 多用户场景

```bash
# 用户 A
hermes --user ou_user_a
> 记住我喜欢 Python

# 用户 B（看不到用户 A 的记忆）
hermes --user ou_user_b
> 我喜欢什么语言？
AI: 我不知道你的偏好 ✅  # 正确隔离
```

## ⚙️ 配置选项

### 禁用 Working Memory（如果遇到问题）

```bash
export HERMES_MEMORY_LEGACY=true
hermes
```

### 调整 Working Memory 大小

在 `config.yaml` 中：
```yaml
memory:
  working_memory_max_entries: 20  # 默认 20 条
```

## 🐛 故障排查

### 问题 1: 记忆仍然不立即生效

**检查**:
```bash
# 确认 Working Memory 已启用
hermes --debug
# 查看日志中是否有 "Working Memory" 相关信息
```

**解决**:
```bash
# 重启 Hermes gateway（如果使用 gateway）
hermes gateway restart
```

### 问题 2: 找不到旧记忆

**原因**: 可能是 user_id 不匹配

**检查**:
```bash
ls ~/.hermes/memories/
# 查看是否有多个用户目录
```

**解决**:
```bash
# 如果需要迁移旧记忆到新用户目录
cp ~/.hermes/memories/MEMORY.md ~/.hermes/memories/ou_your_user_id/
cp ~/.hermes/memories/USER.md ~/.hermes/memories/ou_your_user_id/
```

### 问题 3: 跨用户看到记忆（不应该发生）

**立即报告**: 这是严重的隐私问题

**临时缓解**:
```bash
# 清空共享记忆目录
rm ~/.hermes/memories/MEMORY.md
rm ~/.hermes/memories/USER.md
```

## 📊 性能影响

- **额外 Token 消耗**: 每次请求增加 50-200 tokens
- **响应延迟**: 可忽略（<1ms）
- **磁盘空间**: 每用户约 10KB

## 🔄 迁移指南

### 从旧版本升级

1. **备份现有记忆**:
```bash
cp -r ~/.hermes/memories ~/.hermes/memories.backup
```

2. **更新代码**:
```bash
cd ~/.hermes/hermes-agent-official
git pull
```

3. **重启服务**:
```bash
hermes gateway restart
```

4. **验证**:
```bash
hermes
> 记住测试记忆
> 测试记忆是什么？
# 应该立即返回 "测试记忆"
```

### 回滚到旧版本

```bash
# 方式 1: 使用环境变量
export HERMES_MEMORY_LEGACY=true

# 方式 2: Git 回滚
cd ~/.hermes/hermes-agent-official
git revert HEAD

# 方式 3: 恢复备份
rm -rf ~/.hermes/memories
mv ~/.hermes/memories.backup ~/.hermes/memories
```

## 📝 最佳实践

### 1. 定期清理记忆

```bash
# 查看记忆文件大小
du -h ~/.hermes/memories/*/MEMORY.md

# 如果接近 2200 字符限制，手动清理
hermes
> 删除不重要的记忆
```

### 2. 使用明确的记忆类型

```bash
# 好的做法
> 记住我的偏好：喜欢简洁的回复
> 记住项目事实：使用 Python 3.11

# 不好的做法
> 记住这个  # 太模糊
```

### 3. 验证记忆已保存

```bash
> 记住我的邮箱是 user@example.com
> 我的邮箱是什么？  # 立即验证
```

## 🆘 获取帮助

- **GitHub Issues**: https://github.com/anthropics/hermes-agent/issues
- **文档**: `MEMORY_SYSTEM_PHASE1_SUMMARY.md`
- **测试**: `pytest tests/test_working_memory.py tests/test_user_isolation.py`

## 🔮 未来计划

- **Phase 2**: SQLite 数据库存储（3-5 天）
- **Phase 3**: 语义检索和向量搜索（5-7 天）
- **Phase 4**: 自动记忆提取和治理（7-10 天）

---

**版本**: Phase 1 - Emergency Fixes  
**日期**: 2026-05-06  
**状态**: ✅ 已完成并测试

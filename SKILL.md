---
name: session-manager
description: Claude Code 会话管理 — 列表/搜索/查看/导出/删除/标签/备注/统计。当用户需要管理 Claude Code 历史对话记录时使用，包括：(1) 浏览或搜索历史会话，(2) 查看会话完整内容（含思考过程、工具调用），(3) 导出为 Markdown/JSON/TXT，(4) 删除或批量删除会话，(5) 添加标签和备注，(6) 查看统计分析，(7) 通过 Web UI 可视化管理所有会话。
---

# 会话管理 Skill

管理 Claude Code 的所有历史对话记录。

## 命令行使用

```bash
SM="python3 ~/.claude/skills/session-manager/scripts/session_manager.py"

# 列出最近会话
$SM list
$SM list -n 30 -d 7 -p myproject

# 搜索
$SM search "docker 部署"
$SM search "视频压缩" --ai

# 查看会话内容
$SM show <session_id>
$SM show <session_id> --full

# 导出
$SM export <session_id> -f md
$SM export --all -f md -o ~/exports/

# 删除（自动备份到 trash/）
$SM delete <session_id>

# 标签管理
$SM tag <session_id> work llm
$SM tag --list
$SM tag --filter work

# 备注
$SM note <session_id> "这是备注"

# 统计
$SM stats
$SM stats --by-project
```

## Web UI 使用

一键启动前端和后端：

```bash
~/.claude/skills/session-manager/scripts/start-web.sh
```

或手动分别启动：

```bash
# 后端 API（端口 5001）
python3 ~/.claude/skills/session-manager/scripts/api.py

# 前端（端口 3000）
cd ~/.claude/skills/session-manager/assets/web && npm run dev
```

访问 http://localhost:3000 打开 Web 管理界面。

Web UI 支持：分页浏览、多选批量操作、完整对话内容（思考过程/工具调用/命令行/执行结果）、Markdown 渲染、标签/备注编辑、统计面板、导出。

## 命令速查

| 命令 | 说明 |
|------|------|
| `list` | 列出会话，支持 `-n` `-d` `-p` `--after` `--before` |
| `search` | 关键词/AI 语义搜索，支持 `--ai` `--deep` |
| `show` | 查看会话完整对话，支持 `--full` `-n` |
| `export` | 导出为 md/json/txt，支持 `--all` 批量 |
| `delete` | 删除会话（自动备份），支持 `--force` |
| `tag` | 打标签/移除/列出/按标签过滤 |
| `note` | 设置/查看/清除会话备注 |
| `stats` | 统计总量、按项目/月份/标签分布 |

所有命令的 `session_id` 支持前 8 位短 ID。

#!/usr/bin/env python3
"""
session_manager.py - Claude Code 会话管理工具

功能:
  list    列出最近会话
  search  关键词/AI 语义搜索
  show    查看会话完整内容
  export  导出会话 (md/json/txt)
  delete  删除会话
  tag     打标签
  note    设置备注/标题
  stats   统计信息

用法:
  python3 session_manager.py list [-n 20] [-d 7] [-p project]
  python3 session_manager.py search "关键词" [--ai] [--deep]
  python3 session_manager.py show <session_id>
  python3 session_manager.py export <session_id> [-f md|json|txt] [-o output]
  python3 session_manager.py export --all [-f md] [-o ./exports/]
  python3 session_manager.py delete <session_id> [--force]
  python3 session_manager.py tag <session_id> <tag1> [tag2 ...]
  python3 session_manager.py tag --list
  python3 session_manager.py tag --filter <tag>
  python3 session_manager.py note <session_id> "备注内容"
  python3 session_manager.py stats [--by-project] [--by-month]
"""

import argparse
import json
import os
import re
import shutil
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

SCRIPT_DIR = Path(__file__).parent.parent  # skill 根目录
PROJECTS_DIR = Path("~/.claude/projects").expanduser()
HISTORY_FILE = Path("~/.claude/history.jsonl").expanduser()
META_FILE = SCRIPT_DIR / "session_meta.json"  # 标签/备注持久化


# ---------------------------------------------------------------------------
# 元数据管理（标签 + 备注）
# ---------------------------------------------------------------------------

def load_meta() -> dict:
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_meta(meta: dict):
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def get_session_meta(meta: dict, sid: str) -> dict:
    return meta.get(sid, {"tags": [], "note": ""})

# ---------------------------------------------------------------------------
# 数据解析
# ---------------------------------------------------------------------------

def parse_history() -> dict[str, list[dict]]:
    """解析 history.jsonl，按 sessionId 分组。"""
    if not HISTORY_FILE.exists():
        print(f"❌ 历史文件不存在: {HISTORY_FILE}", file=sys.stderr)
        sys.exit(1)
    groups: dict[str, list[dict]] = defaultdict(list)
    with open(HISTORY_FILE, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                r = json.loads(line)
                sid = r.get("sessionId")
                if sid:
                    groups[sid].append(r)
            except json.JSONDecodeError:
                continue
    return dict(groups)

def get_session_file(sid: str) -> Path | None:
    """找到 session 对应的 JSONL 文件，支持短 ID 前缀匹配。"""
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        # 精确匹配
        f = project_dir / f"{sid}.jsonl"
        if f.exists():
            return f
        # 前缀匹配
        for f in project_dir.glob("*.jsonl"):
            if f.stem.startswith(sid):
                return f
    return None

def read_session_messages(sid: str) -> list[dict]:
    """读取 session 完整对话消息。"""
    f = get_session_file(sid)
    if not f:
        return []
    messages = []
    with open(f, "r", encoding="utf-8", errors="ignore") as fp:
        for line in fp:
            line = line.strip()
            if not line:
                continue
            try:
                messages.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return messages

def get_text_content(content) -> str:
    """从 message content 提取纯文本。"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        parts = []
        for c in content:
            if isinstance(c, dict):
                if c.get("type") == "text":
                    parts.append(c.get("text", ""))
                elif c.get("type") == "tool_use":
                    parts.append(f"[Tool: {c.get('name', '')}]")
                elif c.get("type") == "tool_result":
                    inner = c.get("content", "")
                    if isinstance(inner, list):
                        for ic in inner:
                            if isinstance(ic, dict) and ic.get("type") == "text":
                                parts.append(f"[Result: {ic.get('text','')[:200]}]")
                    elif isinstance(inner, str):
                        parts.append(f"[Result: {inner[:200]}]")
        return "\n".join(parts)
    return ""


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def format_ts(ts) -> str:
    if not ts:
        return "N/A"
    try:
        if isinstance(ts, str):
            return datetime.fromisoformat(ts.replace("Z", "+00:00")).astimezone().strftime("%Y-%m-%d %H:%M")
        return datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
    except Exception:
        return "N/A"

def truncate(text: str, n: int = 80) -> str:
    text = text.replace("\n", " ").strip()
    return text[:n-3] + "..." if len(text) > n else text

def get_session_summary(recs: list[dict]) -> dict:
    """从 history 记录提取会话摘要信息。"""
    sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))
    first_msg = ""
    for r in sorted_recs:
        d = r.get("display", "").strip()
        if d and not (d.startswith("/") and " " not in d.split("\n")[0]):
            first_msg = d
            break
    return {
        "session_id": sorted_recs[0].get("sessionId", "") if sorted_recs else "",
        "first_msg": first_msg,
        "last_time": sorted_recs[-1].get("timestamp", 0) if sorted_recs else 0,
        "first_time": sorted_recs[0].get("timestamp", 0) if sorted_recs else 0,
        "project": sorted_recs[0].get("project", "") if sorted_recs else "",
        "total_messages": len(recs),
    }

def filter_groups(groups, days=None, after=None, before=None, project=None):
    now_ms = datetime.now().timestamp() * 1000
    cutoff_ms = now_ms - days * 86400 * 1000 if days else 0
    if after:
        cutoff_ms = datetime.strptime(after, "%Y-%m-%d").timestamp() * 1000
    end_ms = datetime.strptime(before, "%Y-%m-%d").timestamp() * 1000 if before else float("inf")

    result = {}
    for sid, recs in groups.items():
        max_ts = max(r.get("timestamp", 0) for r in recs)
        if not (cutoff_ms <= max_ts <= end_ms):
            continue
        if project and not any(project.lower() in r.get("project", "").lower() for r in recs):
            continue
        result[sid] = recs
    return result

# ---------------------------------------------------------------------------
# 命令: list
# ---------------------------------------------------------------------------

def cmd_list(args):
    groups = parse_history()
    meta = load_meta()

    if args.days or args.after or args.before or args.project:
        groups = filter_groups(groups, args.days, args.after, args.before, args.project)

    # 按最后时间排序
    sessions = []
    for sid, recs in groups.items():
        s = get_session_summary(recs)
        s["session_id"] = sid
        s["meta"] = get_session_meta(meta, sid)
        sessions.append(s)

    sessions.sort(key=lambda x: -x["last_time"])
    sessions = sessions[:args.limit]

    print(f"\n{'━'*80}")
    print(f"  📋 会话列表 — 共 {len(groups)} 个会话，显示 {len(sessions)} 条")
    print(f"{'━'*80}")

    for i, s in enumerate(sessions, 1):
        sid = s["session_id"]
        tags = s["meta"].get("tags", [])
        note = s["meta"].get("note", "")
        tag_str = "  🏷 " + " ".join(f"#{t}" for t in tags) if tags else ""
        note_str = f"  📝 {note}" if note else ""
        proj = Path(s["project"]).name if s["project"] else "~"

        print(f"\n  {i:>3}. {format_ts(s['last_time'])}  [{sid[:8]}]  {proj}")
        if s["first_msg"]:
            print(f"       💬 {truncate(s['first_msg'], 70)}")
        if tag_str:
            print(f"      {tag_str}")
        if note_str:
            print(f"      {note_str}")

    print(f"\n{'━'*80}")
    print("  恢复: claude --resume <session_id>")
    print(f"{'━'*80}\n")


# ---------------------------------------------------------------------------
# 命令: show
# ---------------------------------------------------------------------------

def cmd_show(args):
    sid = args.session_id
    messages = read_session_messages(sid)
    if not messages:
        print(f"❌ 未找到会话: {sid}")
        return

    meta = load_meta()
    m = get_session_meta(meta, sid)
    note = m.get("note", "")
    tags = m.get("tags", [])

    print(f"\n{'━'*80}")
    print(f"  📖 会话详情: {sid}")
    if note:
        print(f"  📝 备注: {note}")
    if tags:
        print(f"  🏷  标签: {' '.join('#'+t for t in tags)}")
    print(f"{'━'*80}\n")

    limit = args.limit or 999999
    count = 0
    # 系统内容过滤模式
    SYSTEM_PATTERNS = [
        "<local-command-caveat>", "<command-name>", "<command-message>",
        "<command-args>", "<local-command-stdout>", "<system-reminder>",
        "<task-notification>",
    ]
    for msg in messages:
        if count >= limit:
            print(f"  ... (已截断，共 {len(messages)} 条消息)")
            break
        # 跳过非对话类型
        if msg.get("type") not in ("user", "assistant"):
            continue
        # 跳过 meta 消息（slash 命令等）
        if msg.get("isMeta"):
            continue

        inner_role = msg.get("message", {}).get("role", "")
        if inner_role == "user":
            role_label = "👤 用户"
        elif inner_role == "assistant":
            role_label = "🤖 Claude"
        else:
            continue

        content_raw = msg.get("message", {}).get("content", "")
        text = get_text_content(content_raw).strip()
        if not text:
            continue
        # 过滤纯系统标签消息
        if any(p in text for p in SYSTEM_PATTERNS):
            continue

        ts = msg.get("timestamp", "")
        time_str = format_ts(ts) if ts else ""

        print(f"  ── {role_label}  {time_str}")
        # 截断超长内容
        if not args.full and len(text) > 500:
            text = text[:500] + f"\n  ... [共 {len(text)} 字，用 --full 查看完整]"
        for line in text.split("\n"):
            print(f"  {line}")
        print()
        count += 1

    print(f"{'━'*80}")
    print(f"  共 {count} 条消息  |  claude --resume {sid}")
    print(f"{'━'*80}\n")

# ---------------------------------------------------------------------------
# 命令: export
# ---------------------------------------------------------------------------

SYSTEM_PATTERNS = [
    "<local-command-caveat>", "<command-name>", "<command-message>",
    "<command-args>", "<local-command-stdout>", "<system-reminder>",
    "<task-notification>",
]

def is_clean_message(msg: dict) -> tuple[bool, str, str]:
    """返回 (是否保留, role_label, text)"""
    if msg.get("type") not in ("user", "assistant"):
        return False, "", ""
    if msg.get("isMeta"):
        return False, "", ""
    inner_role = msg.get("message", {}).get("role", "")
    if inner_role == "user":
        label = "用户"
    elif inner_role == "assistant":
        label = "Claude"
    else:
        return False, "", ""
    content_raw = msg.get("message", {}).get("content", "")
    text = get_text_content(content_raw).strip()
    if not text:
        return False, "", ""
    if any(p in text for p in SYSTEM_PATTERNS):
        return False, "", ""
    # 过滤纯 tool 调用/结果行
    if text.startswith("[Tool:") or text.startswith("[Result:"):
        return False, "", ""
    return True, label, text

def export_one(sid: str, messages: list[dict], fmt: str, out_dir: Path, meta: dict) -> Path:
    m = get_session_meta(meta, sid)
    note = m.get("note", "") or sid[:8]
    safe_note = re.sub(r'[^\w\u4e00-\u9fff\-]', '_', note)[:40]
    filename = f"{sid[:8]}_{safe_note}.{fmt}"
    out_path = out_dir / filename

    if fmt == "json":
        clean = [msg for msg in messages if is_clean_message(msg)[0]]
        out_path.write_text(json.dumps(clean, ensure_ascii=False, indent=2), encoding="utf-8")

    elif fmt == "txt":
        lines = []
        for msg in messages:
            ok, label, text = is_clean_message(msg)
            if ok:
                ts = format_ts(msg.get("timestamp", ""))
                lines.append(f"[{label}] {ts}\n{text}\n")
        out_path.write_text("\n".join(lines), encoding="utf-8")

    elif fmt == "md":
        lines = [f"# 会话 {sid[:8]}", ""]
        if m.get("note"):
            lines += [f"> 备注: {m['note']}", ""]
        if m.get("tags"):
            lines += [f"> 标签: {' '.join('#'+t for t in m['tags'])}", ""]
        for msg in messages:
            ok, label, text = is_clean_message(msg)
            if ok:
                ts = format_ts(msg.get("timestamp", ""))
                lines += [f"## {label}  `{ts}`", "", text, ""]
        out_path.write_text("\n".join(lines), encoding="utf-8")

    return out_path

def cmd_export(args):
    meta = load_meta()
    fmt = args.format
    out_dir = Path(args.output).expanduser() if args.output else Path.cwd()
    out_dir.mkdir(parents=True, exist_ok=True)

    if args.all:
        groups = parse_history()
        sids = list(groups.keys())
        print(f"📦 批量导出 {len(sids)} 个会话 → {out_dir}")
        for sid in sids:
            messages = read_session_messages(sid)
            if messages:
                p = export_one(sid, messages, fmt, out_dir, meta)
                print(f"  ✅ {p.name}")
        print(f"\n✅ 导出完成: {out_dir}")
    else:
        sid = args.session_id
        messages = read_session_messages(sid)
        if not messages:
            print(f"❌ 未找到会话: {sid}")
            return
        p = export_one(sid, messages, fmt, out_dir, meta)
        print(f"✅ 已导出: {p}")


# ---------------------------------------------------------------------------
# 命令: delete
# ---------------------------------------------------------------------------

def cmd_delete(args):
    sid = args.session_id
    f = get_session_file(sid)
    if not f:
        print(f"❌ 未找到会话文件: {sid}")
        return

    print(f"⚠️  即将删除会话: {sid}")
    print(f"   文件: {f}")
    print(f"   大小: {f.stat().st_size / 1024:.1f} KB")

    if not args.force:
        confirm = input("确认删除? [y/N] ").strip().lower()
        if confirm != "y":
            print("已取消")
            return

    # 备份到 trash 目录
    trash_dir = SCRIPT_DIR / "trash"
    trash_dir.mkdir(exist_ok=True)
    backup = trash_dir / f"{sid}.jsonl"
    shutil.copy2(f, backup)
    f.unlink()

    # 清理元数据
    meta = load_meta()
    if sid in meta:
        del meta[sid]
        save_meta(meta)

    print(f"✅ 已删除（备份至 {backup}）")

# ---------------------------------------------------------------------------
# 命令: tag
# ---------------------------------------------------------------------------

def cmd_tag(args):
    meta = load_meta()

    if args.list:
        # 列出所有标签及其会话数
        tag_count: dict[str, int] = defaultdict(int)
        for m in meta.values():
            for t in m.get("tags", []):
                tag_count[t] += 1
        if not tag_count:
            print("暂无标签")
            return
        print("\n🏷  所有标签:\n")
        for tag, cnt in sorted(tag_count.items(), key=lambda x: -x[1]):
            print(f"  #{tag}  ({cnt} 个会话)")
        print()
        return

    if args.filter:
        # 按标签过滤会话
        groups = parse_history()
        matched = []
        for sid, recs in groups.items():
            m = get_session_meta(meta, sid)
            if args.filter in m.get("tags", []):
                s = get_session_summary(recs)
                s["session_id"] = sid
                matched.append(s)
        matched.sort(key=lambda x: -x["last_time"])
        print(f"\n🏷  标签 #{args.filter} 的会话 ({len(matched)} 个):\n")
        for s in matched:
            print(f"  [{s['session_id'][:8]}]  {format_ts(s['last_time'])}  {truncate(s['first_msg'], 60)}")
        print()
        return

    if args.remove:
        # 移除标签
        sid = args.session_id
        m = get_session_meta(meta, sid)
        tags = m.get("tags", [])
        removed = [t for t in args.tags if t in tags]
        m["tags"] = [t for t in tags if t not in args.tags]
        meta[sid] = m
        save_meta(meta)
        print(f"✅ 已移除标签: {' '.join('#'+t for t in removed)}")
        return

    # 添加标签
    sid = args.session_id
    if not sid:
        print("❌ 请指定 session_id")
        return
    m = get_session_meta(meta, sid)
    existing = set(m.get("tags", []))
    new_tags = [t for t in args.tags if t not in existing]
    m["tags"] = list(existing) + new_tags
    meta[sid] = m
    save_meta(meta)
    print(f"✅ [{sid[:8]}] 标签: {' '.join('#'+t for t in m['tags'])}")

# ---------------------------------------------------------------------------
# 命令: note
# ---------------------------------------------------------------------------

def cmd_note(args):
    meta = load_meta()
    sid = args.session_id
    m = get_session_meta(meta, sid)

    if args.clear:
        m["note"] = ""
        meta[sid] = m
        save_meta(meta)
        print(f"✅ [{sid[:8]}] 备注已清除")
        return

    if args.text:
        m["note"] = args.text
        meta[sid] = m
        save_meta(meta)
        print(f"✅ [{sid[:8]}] 备注: {args.text}")
    else:
        # 显示当前备注
        note = m.get("note", "")
        print(f"[{sid[:8]}] 备注: {note or '(无)'}")


# ---------------------------------------------------------------------------
# 命令: stats
# ---------------------------------------------------------------------------

def cmd_stats(args):
    groups = parse_history()
    meta = load_meta()

    total_sessions = len(groups)
    total_msgs = sum(len(recs) for recs in groups.values())

    # 按项目统计
    project_count: dict[str, int] = defaultdict(int)
    project_msgs: dict[str, int] = defaultdict(int)
    # 按月统计
    month_count: dict[str, int] = defaultdict(int)
    # 标签统计
    tag_count: dict[str, int] = defaultdict(int)

    for sid, recs in groups.items():
        sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))
        proj = sorted_recs[0].get("project", "unknown") if sorted_recs else "unknown"
        proj_name = Path(proj).name or "~"
        project_count[proj_name] += 1
        project_msgs[proj_name] += len(recs)

        last_ts = sorted_recs[-1].get("timestamp", 0)
        if last_ts:
            month = datetime.fromtimestamp(last_ts / 1000).strftime("%Y-%m")
            month_count[month] += 1

        m = get_session_meta(meta, sid)
        for t in m.get("tags", []):
            tag_count[t] += 1

    print(f"\n{'━'*60}")
    print(f"  📊 会话统计")
    print(f"{'━'*60}")
    print(f"  总会话数:   {total_sessions}")
    print(f"  总消息数:   {total_msgs}")
    print(f"  平均消息数: {total_msgs/total_sessions:.1f} 条/会话" if total_sessions else "")
    print(f"  已打标签:   {len([s for s in meta.values() if s.get('tags')])}")
    print(f"  已加备注:   {len([s for s in meta.values() if s.get('note')])}")

    if args.by_project or not (args.by_month):
        print(f"\n  📁 按项目 (Top 10):")
        for proj, cnt in sorted(project_count.items(), key=lambda x: -x[1])[:10]:
            bar = "█" * min(cnt, 30)
            print(f"  {proj:<30} {bar} {cnt}")

    if args.by_month or not (args.by_project):
        print(f"\n  📅 按月份:")
        for month in sorted(month_count.keys(), reverse=True)[:12]:
            cnt = month_count[month]
            bar = "█" * min(cnt, 30)
            print(f"  {month}  {bar} {cnt}")

    if tag_count:
        print(f"\n  🏷  标签分布:")
        for tag, cnt in sorted(tag_count.items(), key=lambda x: -x[1]):
            print(f"  #{tag:<20} {cnt}")

    print(f"\n{'━'*60}\n")

# ---------------------------------------------------------------------------
# 命令: search (复用 search_session.py 逻辑的简化版)
# ---------------------------------------------------------------------------

def cmd_search(args):
    """简单关键词搜索，复用现有逻辑。"""
    import subprocess
    script = Path(__file__).parent / "search_session.py"
    cmd = ["python3", str(script), args.query]
    if args.limit:
        cmd += ["-n", str(args.limit)]
    if args.days:
        cmd += ["-d", str(args.days)]
    if args.project:
        cmd += ["-p", args.project]
    if args.deep:
        cmd.append("--deep")
    if args.ai:
        cmd.append("--ai")
    if args.verbose:
        cmd.append("-v")
    os.execv(sys.executable, [sys.executable] + cmd[1:] if cmd[0] == "python3" else cmd)


# ---------------------------------------------------------------------------
# 主入口 & 参数解析
# ---------------------------------------------------------------------------

def main():
    parser = argparse.ArgumentParser(
        prog="session_manager.py",
        description="📋 Claude Code 会话管理工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  list    python3 session_manager.py list -n 20
  list    python3 session_manager.py list -d 7 -p myproject
  show    python3 session_manager.py show abc12345
  show    python3 session_manager.py show abc12345 --full
  export  python3 session_manager.py export abc12345 -f md
  export  python3 session_manager.py export --all -f md -o ~/exports/
  delete  python3 session_manager.py delete abc12345
  tag     python3 session_manager.py tag abc12345 work llm
  tag     python3 session_manager.py tag --list
  tag     python3 session_manager.py tag --filter work
  tag     python3 session_manager.py tag abc12345 work --remove
  note    python3 session_manager.py note abc12345 "配置 JMF 端口转发"
  stats   python3 session_manager.py stats
  search  python3 session_manager.py search "docker 部署" --ai
        """
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- list ---
    p_list = sub.add_parser("list", help="列出最近会话")
    p_list.add_argument("-n", "--limit", type=int, default=20)
    p_list.add_argument("-d", "--days", type=int)
    p_list.add_argument("--after")
    p_list.add_argument("--before")
    p_list.add_argument("-p", "--project")

    # --- show ---
    p_show = sub.add_parser("show", help="查看会话完整内容")
    p_show.add_argument("session_id")
    p_show.add_argument("-n", "--limit", type=int, default=None, help="最多显示消息数")
    p_show.add_argument("--full", action="store_true", help="显示完整内容（不截断）")

    # --- export ---
    p_export = sub.add_parser("export", help="导出会话")
    p_export.add_argument("session_id", nargs="?", default=None)
    p_export.add_argument("-f", "--format", choices=["md", "json", "txt"], default="md")
    p_export.add_argument("-o", "--output", default=None, help="输出目录（默认当前目录）")
    p_export.add_argument("--all", action="store_true", help="导出所有会话")

    # --- delete ---
    p_del = sub.add_parser("delete", help="删除会话")
    p_del.add_argument("session_id")
    p_del.add_argument("--force", action="store_true", help="跳过确认")

    # --- tag ---
    p_tag = sub.add_parser("tag", help="管理标签")
    p_tag.add_argument("session_id", nargs="?", default=None)
    p_tag.add_argument("tags", nargs="*", help="标签名")
    p_tag.add_argument("--list", action="store_true", help="列出所有标签")
    p_tag.add_argument("--filter", metavar="TAG", help="按标签过滤会话")
    p_tag.add_argument("--remove", action="store_true", help="移除标签")

    # --- note ---
    p_note = sub.add_parser("note", help="设置会话备注")
    p_note.add_argument("session_id")
    p_note.add_argument("text", nargs="?", default=None, help="备注内容")
    p_note.add_argument("--clear", action="store_true", help="清除备注")

    # --- stats ---
    p_stats = sub.add_parser("stats", help="统计信息")
    p_stats.add_argument("--by-project", action="store_true")
    p_stats.add_argument("--by-month", action="store_true")

    # --- search ---
    p_search = sub.add_parser("search", help="搜索会话（复用 search_session.py）")
    p_search.add_argument("query")
    p_search.add_argument("-n", "--limit", type=int, default=None)
    p_search.add_argument("-d", "--days", type=int)
    p_search.add_argument("-p", "--project")
    p_search.add_argument("--deep", action="store_true")
    p_search.add_argument("--ai", action="store_true")
    p_search.add_argument("-v", "--verbose", action="store_true")

    args = parser.parse_args()

    dispatch = {
        "list": cmd_list,
        "show": cmd_show,
        "export": cmd_export,
        "delete": cmd_delete,
        "tag": cmd_tag,
        "note": cmd_note,
        "stats": cmd_stats,
        "search": cmd_search,
    }
    dispatch[args.command](args)


if __name__ == "__main__":
    main()

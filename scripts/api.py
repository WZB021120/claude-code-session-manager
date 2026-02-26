#!/usr/bin/env python3
"""
Session Manager Web API
Flask 服务器，直接读取和处理会话数据
"""

from flask import Flask, jsonify, request, send_file
from flask_cors import CORS
import json
import os
from pathlib import Path
from datetime import datetime
from collections import defaultdict

app = Flask(__name__)
CORS(app)

SCRIPT_DIR = Path(__file__).parent.parent  # skill 根目录
PROJECTS_DIR = Path("~/.claude/projects").expanduser()
META_FILE = SCRIPT_DIR / "session_meta.json"

# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------

def extract_text_content(content):
    """
    从 message.content 中提取纯文本。
    - 用户消息：content 通常是字符串
    - 助手消息：content 通常是列表，包含 {type: "thinking", ...} 和 {type: "text", text: "..."}
    """
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict):
                if item.get("type") == "text":
                    texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)
    return str(content) if content else ""


def is_system_command(content_text):
    """判断是否为系统命令消息"""
    if not content_text:
        return False
    return content_text.startswith("<local-command") or content_text.startswith("<command-")

# ---------------------------------------------------------------------------
# 数据读取函数
# ---------------------------------------------------------------------------

def load_meta():
    """加载元数据（标签和备注）"""
    if META_FILE.exists():
        try:
            return json.loads(META_FILE.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}

def save_meta(meta):
    """保存元数据"""
    META_FILE.write_text(json.dumps(meta, ensure_ascii=False, indent=2), encoding="utf-8")

def parse_history():
    """扫描所有项目目录，收集会话信息"""
    if not PROJECTS_DIR.exists():
        return {}

    sessions = {}
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue

        for session_file in project_dir.glob("*.jsonl"):
            sid = session_file.stem
            if sid not in sessions:
                try:
                    with open(session_file, "r", encoding="utf-8") as f:
                        # 读取找到第一个有 timestamp 的记录
                        timestamp = ""
                        for line in f:
                            line = line.strip()
                            if not line:
                                continue
                            try:
                                record = json.loads(line)
                                # timestamp 在记录顶层
                                ts = record.get("timestamp", "")
                                if ts:
                                    timestamp = ts
                                    break
                                # 也可能在 snapshot 中
                                if "snapshot" in record:
                                    ts = record["snapshot"].get("timestamp", "")
                                    if ts:
                                        timestamp = ts
                                        break
                            except json.JSONDecodeError:
                                continue

                        sessions[sid] = {
                            "id": sid,
                            "project": project_dir.name,
                            "timestamp": timestamp,
                            "file": str(session_file)
                        }
                except Exception:
                    continue

    return sessions

def get_session_file(sid):
    """找到 session 对应的 JSONL 文件"""
    for project_dir in PROJECTS_DIR.iterdir():
        if not project_dir.is_dir():
            continue
        # 精确匹配
        f = project_dir / f"{sid}.jsonl"
        if f.exists():
            return f
        # 前缀匹配（支持短 ID）
        for f in project_dir.glob("*.jsonl"):
            if f.stem.startswith(sid):
                return f
    return None

def extract_tool_result_text(content):
    """从 tool_result 的 content 中提取文本"""
    if isinstance(content, str):
        return content
    if isinstance(content, list):
        texts = []
        for item in content:
            if isinstance(item, dict) and item.get("type") == "text":
                texts.append(item.get("text", ""))
            elif isinstance(item, str):
                texts.append(item)
        return "\n".join(texts)
    return str(content) if content else ""


def parse_content_blocks(raw_content):
    """
    将 message.content 解析为结构化的 blocks 列表。
    每个 block 有 type 和对应字段。
    """
    if isinstance(raw_content, str):
        if not raw_content.strip():
            return []
        return [{"type": "text", "text": raw_content}]

    if not isinstance(raw_content, list):
        return [{"type": "text", "text": str(raw_content)}] if raw_content else []

    blocks = []
    for item in raw_content:
        if isinstance(item, str):
            if item.strip():
                blocks.append({"type": "text", "text": item})
            continue
        if not isinstance(item, dict):
            continue

        block_type = item.get("type", "")

        if block_type == "text":
            text = item.get("text", "")
            if text.strip():
                blocks.append({"type": "text", "text": text})

        elif block_type == "thinking":
            thinking = item.get("thinking", "")
            if thinking.strip():
                blocks.append({"type": "thinking", "text": thinking})

        elif block_type == "tool_use":
            tool_input = item.get("input", {})
            block = {
                "type": "tool_use",
                "tool_name": item.get("name", "unknown"),
                "tool_id": item.get("id", ""),
            }
            # 根据工具类型提取关键信息
            name = item.get("name", "")
            if name == "Bash":
                block["command"] = tool_input.get("command", "")
                block["description"] = tool_input.get("description", "")
            elif name in ("Write", "Edit"):
                block["file_path"] = tool_input.get("file_path", tool_input.get("filePath", ""))
                block["description"] = tool_input.get("description", "")
            elif name == "Read":
                block["file_path"] = tool_input.get("file_path", tool_input.get("filePath", ""))
            elif name in ("Task", "TodoWrite"):
                block["description"] = tool_input.get("description", tool_input.get("prompt", ""))
            else:
                # 通用工具，保留 input 摘要
                block["input_summary"] = json.dumps(tool_input, ensure_ascii=False)[:500] if tool_input else ""
            blocks.append(block)

        elif block_type == "tool_result":
            result_content = extract_tool_result_text(item.get("content", ""))
            if result_content.strip():
                blocks.append({
                    "type": "tool_result",
                    "tool_id": item.get("tool_use_id", ""),
                    "text": result_content[:5000],  # 限制结果长度
                    "is_error": item.get("is_error", False)
                })

    return blocks


def load_session_messages(sid):
    """加载会话的所有消息，返回结构化内容块"""
    session_file = get_session_file(sid)
    if not session_file:
        return []

    messages = []
    with open(session_file, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                record = json.loads(line)
                record_type = record.get("type", "")

                # 只处理 user 和 assistant 类型的记录
                if record_type not in ("user", "assistant"):
                    continue

                msg = record.get("message", {})
                role = msg.get("role", record_type)
                raw_content = msg.get("content", "")

                # 解析为结构化内容块
                blocks = parse_content_blocks(raw_content)

                # 过滤掉系统命令消息（仅对纯文本用户消息）
                if role == "user" and len(blocks) == 1 and blocks[0]["type"] == "text":
                    if is_system_command(blocks[0]["text"]):
                        continue

                if not blocks:
                    continue

                # 提取纯文本（向后兼容 + 用于 content 字段）
                text_content = extract_text_content(raw_content)

                messages.append({
                    "role": role,
                    "content": text_content,
                    "blocks": blocks,
                    "timestamp": record.get("timestamp", "")
                })
            except json.JSONDecodeError:
                continue
    return messages

def format_session_info(sid, session_data, meta):
    """格式化会话信息"""
    session_meta = meta.get(sid, {"tags": [], "note": ""})

    # 读取会话文件获取标题和消息计数
    title = "未命名会话"
    message_count = 0
    last_timestamp = session_data.get("timestamp", "")

    try:
        session_file = Path(session_data["file"])
        if session_file.exists():
            with open(session_file, "r", encoding="utf-8") as f:
                for line in f:
                    try:
                        record = json.loads(line.strip())
                        record_type = record.get("type", "")

                        if record_type not in ("user", "assistant"):
                            continue

                        msg = record.get("message", {})
                        raw_content = msg.get("content", "")
                        text_content = extract_text_content(raw_content)

                        # 跳过系统命令
                        if is_system_command(text_content):
                            continue

                        if not text_content.strip():
                            continue

                        if record_type == "user":
                            if title == "未命名会话":
                                title = text_content[:80].replace("\n", " ")
                                if len(text_content) > 80:
                                    title += "..."
                            message_count += 1
                        elif record_type == "assistant":
                            message_count += 1

                        # 更新最新的时间戳
                        ts = record.get("timestamp", "")
                        if ts:
                            last_timestamp = ts
                    except Exception:
                        continue
    except Exception:
        pass

    return {
        "id": sid,
        "title": title,
        "created_at": session_data.get("timestamp", ""),
        "updated_at": last_timestamp,
        "message_count": message_count,
        "project": session_data.get("project", ""),
        "tags": session_meta.get("tags", []),
        "note": session_meta.get("note", "")
    }

# ---------------------------------------------------------------------------
# API 路由
# ---------------------------------------------------------------------------

@app.route('/api/sessions', methods=['GET'])
def list_sessions():
    """获取会话列表（支持分页）"""
    try:
        page = int(request.args.get('page', '1'))
        page_size = int(request.args.get('page_size', '20'))
        if page < 1:
            page = 1
        if page_size < 1:
            page_size = 20
        if page_size > 100:
            page_size = 100

        sessions_data = parse_history()
        meta = load_meta()

        # 按时间戳排序
        sorted_sessions = sorted(
            sessions_data.items(),
            key=lambda x: x[1].get("timestamp", ""),
            reverse=True
        )

        total = len(sorted_sessions)
        total_pages = (total + page_size - 1) // page_size
        start = (page - 1) * page_size
        end = start + page_size
        page_sessions = sorted_sessions[start:end]

        sessions = []
        for sid, session_data in page_sessions:
            sessions.append(format_session_info(sid, session_data, meta))

        return jsonify({
            "sessions": sessions,
            "total": total,
            "page": page,
            "page_size": page_size,
            "total_pages": total_pages
        })
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>', methods=['GET'])
def get_session(session_id):
    """获取单个会话详情"""
    try:
        sessions_data = parse_history()
        meta = load_meta()

        # 支持短 ID 匹配
        matched_id = None
        for sid in sessions_data:
            if sid == session_id or sid.startswith(session_id):
                matched_id = sid
                break

        if not matched_id:
            return jsonify({"error": "会话不存在"}), 404

        session_data = sessions_data[matched_id]
        messages = load_session_messages(matched_id)

        session_info = format_session_info(matched_id, session_data, meta)
        session_info["messages"] = messages

        return jsonify(session_info)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>', methods=['DELETE'])
def delete_session(session_id):
    """删除会话（移动到 trash）"""
    try:
        session_file = get_session_file(session_id)
        if not session_file:
            return jsonify({"error": "会话不存在"}), 404

        # 创建 trash 目录
        trash_dir = SCRIPT_DIR / "trash"
        trash_dir.mkdir(exist_ok=True)

        # 移动文件
        import shutil
        shutil.move(str(session_file), str(trash_dir / session_file.name))

        return jsonify({"message": "删除成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/batch-delete', methods=['POST'])
def batch_delete_sessions():
    """批量删除会话"""
    try:
        ids = request.json.get('ids', [])
        if not ids:
            return jsonify({"error": "请提供要删除的会话 ID"}), 400

        import shutil
        trash_dir = SCRIPT_DIR / "trash"
        trash_dir.mkdir(exist_ok=True)

        deleted = []
        failed = []
        for sid in ids:
            session_file = get_session_file(sid)
            if session_file:
                try:
                    shutil.move(str(session_file), str(trash_dir / session_file.name))
                    deleted.append(sid)
                except Exception:
                    failed.append(sid)
            else:
                failed.append(sid)

        return jsonify({"deleted": deleted, "failed": failed, "message": f"成功删除 {len(deleted)} 个会话"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/export', methods=['GET'])
def export_session(session_id):
    """导出会话"""
    try:
        format_type = request.args.get('format', 'md')
        messages = load_session_messages(session_id)

        if not messages:
            return jsonify({"error": "会话不存在"}), 404

        # 生成导出内容
        if format_type == 'json':
            content = json.dumps(messages, ensure_ascii=False, indent=2)
            mimetype = 'application/json'
        elif format_type == 'txt':
            lines = []
            for msg in messages:
                lines.append(f"[{msg['role'].upper()}]")
                lines.append(msg['content'])
                lines.append("")
            content = "\n".join(lines)
            mimetype = 'text/plain'
        else:  # markdown
            lines = [f"# Session {session_id[:8]}", ""]
            for msg in messages:
                role = "用户" if msg['role'] == 'user' else "Claude"
                lines.append(f"## {role}")
                lines.append(msg['content'])
                lines.append("")
            content = "\n".join(lines)
            mimetype = 'text/markdown'

        # 写入临时文件
        temp_file = f"/tmp/session-{session_id[:8]}.{format_type}"
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write(content)

        return send_file(temp_file, as_attachment=True, mimetype=mimetype)
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/search', methods=['GET'])
def search_sessions():
    """搜索会话"""
    try:
        query = request.args.get('q', '').lower()
        if not query:
            return jsonify([])

        sessions_data = parse_history()
        meta = load_meta()
        results = []

        for sid, session_data in sessions_data.items():
            # 先检查标题/项目名是否匹配
            info = format_session_info(sid, session_data, meta)
            if query in info["title"].lower() or query in info["project"].lower():
                results.append(info)
                continue

            # 搜索消息内容
            session_file = get_session_file(sid)
            if not session_file:
                continue

            found = False
            try:
                with open(session_file, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line:
                            continue
                        try:
                            record = json.loads(line)
                            record_type = record.get("type", "")
                            if record_type not in ("user", "assistant"):
                                continue
                            msg = record.get("message", {})
                            text_content = extract_text_content(msg.get("content", ""))
                            if query in text_content.lower():
                                results.append(info)
                                found = True
                                break
                        except json.JSONDecodeError:
                            continue
            except Exception:
                continue

            if found:
                continue

        return jsonify(results)
    except Exception as e:
        import traceback
        traceback.print_exc()
        return jsonify({"error": str(e)}), 500

@app.route('/api/stats', methods=['GET'])
def get_stats():
    """获取统计信息"""
    try:
        sessions_data = parse_history()

        # 按项目统计
        by_project = defaultdict(int)
        by_month = defaultdict(int)

        for sid, session_data in sessions_data.items():
            project = session_data.get("project", "unknown")
            by_project[project] += 1

            # 按月份统计
            ts = session_data.get("timestamp", "")
            if ts:
                try:
                    month = ts[:7]  # "2026-01"
                    by_month[month] += 1
                except Exception:
                    pass

        # 按数量排序项目
        sorted_projects = dict(sorted(by_project.items(), key=lambda x: x[1], reverse=True))
        sorted_months = dict(sorted(by_month.items(), reverse=True))

        return jsonify({
            "total": len(sessions_data),
            "by_project": sorted_projects,
            "by_month": sorted_months
        })
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/tags', methods=['POST'])
def add_tags(session_id):
    """添加标签"""
    try:
        tags = request.json.get('tags', [])
        if not tags:
            return jsonify({"error": "标签不能为空"}), 400

        meta = load_meta()
        if session_id not in meta:
            meta[session_id] = {"tags": [], "note": ""}

        for tag in tags:
            if tag not in meta[session_id]["tags"]:
                meta[session_id]["tags"].append(tag)

        save_meta(meta)
        return jsonify({"message": "标签添加成功", "tags": meta[session_id]["tags"]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/tags', methods=['DELETE'])
def remove_tags(session_id):
    """移除标签"""
    try:
        tags = request.json.get('tags', [])
        if not tags:
            return jsonify({"error": "标签不能为空"}), 400

        meta = load_meta()
        if session_id in meta:
            for tag in tags:
                if tag in meta[session_id]["tags"]:
                    meta[session_id]["tags"].remove(tag)

        save_meta(meta)
        return jsonify({"message": "标签移除成功", "tags": meta.get(session_id, {}).get("tags", [])})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/note', methods=['GET'])
def get_note(session_id):
    """获取备注"""
    try:
        meta = load_meta()
        note = meta.get(session_id, {}).get("note", "")
        return jsonify({"note": note})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/note', methods=['POST'])
def set_note(session_id):
    """设置备注"""
    try:
        note = request.json.get('note', '')

        meta = load_meta()
        if session_id not in meta:
            meta[session_id] = {"tags": [], "note": ""}

        meta[session_id]["note"] = note
        save_meta(meta)

        return jsonify({"message": "备注设置成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/api/sessions/<session_id>/note', methods=['DELETE'])
def clear_note(session_id):
    """清除备注"""
    try:
        meta = load_meta()
        if session_id in meta:
            meta[session_id]["note"] = ""
            save_meta(meta)

        return jsonify({"message": "备注清除成功"})
    except Exception as e:
        return jsonify({"error": str(e)}), 500

if __name__ == '__main__':
    print("🚀 Session Manager API 启动中...")
    print("📍 前端地址: http://localhost:3000")
    print("📍 API 地址: http://localhost:5001")
    app.run(debug=True, port=5001)

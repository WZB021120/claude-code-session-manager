#!/usr/bin/env python3
"""
search_session.py - Claude Code 历史会话搜索工具

搜索 ~/.claude/history.jsonl 中的历史对话记录，
支持关键词搜索、时间过滤、深度搜索和 AI 语义搜索。

AI 语义搜索采用两阶段架构:
  1. Embedding 向量召回 (doubao-embedding) — 语义相似度匹配
  2. LLM Rerank + 摘要 (GLM-4-7) — 精排和生成摘要

依赖: pyyaml, openai (仅 --ai 模式), numpy (仅 --ai 模式)
"""

import argparse
import hashlib
import json
import os
import re
import sys
from collections import defaultdict
from datetime import datetime, timedelta
from pathlib import Path

# ---------------------------------------------------------------------------
# 配置加载
# ---------------------------------------------------------------------------

SCRIPT_DIR = Path(__file__).parent.parent  # skill 根目录
INDEX_DIR = SCRIPT_DIR / "index"  # 向量索引持久化目录
DEFAULT_CONFIG = {
    "paths": {
        "history_file": "~/.claude/history.jsonl",
        "projects_dir": "~/.claude/projects",
    },
    "search": {
        "default_limit": 20,
        "max_display_length": 100,
    },
    "embedding": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "doubao-embedding-vision-251215",
        "batch_size": 20,       # 每批嵌入的文本数
        "top_k": 30,            # 向量召回的候选数量
        "similarity_threshold": 0.3,  # 最低相似度阈值
    },
    "rerank": {
        "base_url": "https://ark.cn-beijing.volces.com/api/v3",
        "model": "glm-4-7-251222",
        "timeout": 30,
        "temperature": 0.3,
        "max_candidates": 15,   # 送入 LLM 精排的最大候选数
    },
}


def load_config() -> dict:
    """加载配置文件，缺失时使用默认值。"""
    import copy
    config = copy.deepcopy(DEFAULT_CONFIG)
    config_path = SCRIPT_DIR / "config.yaml"
    if config_path.exists():
        try:
            import yaml
            with open(config_path, "r", encoding="utf-8") as f:
                user_cfg = yaml.safe_load(f) or {}
            for section, values in user_cfg.items():
                if isinstance(values, dict) and section in config:
                    config[section].update(values)
                else:
                    config[section] = values
        except ImportError:
            pass
    return config


# ---------------------------------------------------------------------------
# 数据解析
# ---------------------------------------------------------------------------


def parse_history(history_file: str) -> list[dict]:
    """解析 history.jsonl，返回记录列表。"""
    path = Path(history_file).expanduser()
    if not path.exists():
        print(f"❌ 历史文件不存在: {path}", file=sys.stderr)
        sys.exit(1)

    records = []
    with open(path, "r", encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                records.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    return records


def group_by_session(records: list[dict]) -> dict[str, list[dict]]:
    """按 sessionId 分组。"""
    groups: dict[str, list[dict]] = defaultdict(list)
    for r in records:
        sid = r.get("sessionId")
        if sid:
            groups[sid].append(r)
    return dict(groups)


# ---------------------------------------------------------------------------
# 工具函数
# ---------------------------------------------------------------------------


def get_user_inputs(recs: list[dict], max_count: int = 5) -> list[str]:
    """从会话记录中获取多条有意义的用户输入（跳过 slash 命令）。"""
    sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))
    inputs = []
    for r in sorted_recs:
        display = r.get("display", "").strip()
        if not display:
            continue
        if display.startswith("/") and " " not in display.split("\n")[0]:
            continue
        inputs.append(display)
        if len(inputs) >= max_count:
            break
    return inputs


def get_first_user_input(recs: list[dict]) -> str:
    """从会话记录中找到第一条有意义的用户输入（跳过 slash 命令）。"""
    inputs = get_user_inputs(recs, max_count=1)
    if inputs:
        return inputs[0]
    sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))
    if sorted_recs:
        return sorted_recs[-1].get("display", "")
    return ""


def get_session_text(recs: list[dict]) -> str:
    """将会话的所有用户输入拼接为单一文本，用于向量化。"""
    sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))
    texts = []
    for r in sorted_recs:
        display = r.get("display", "").strip()
        if display and not (display.startswith("/") and " " not in display.split("\n")[0]):
            texts.append(display)
    return "\n".join(texts)


def format_timestamp(ts_ms: float) -> str:
    """毫秒时间戳转可读格式。"""
    if ts_ms <= 0:
        return "N/A"
    try:
        return datetime.fromtimestamp(ts_ms / 1000).strftime("%Y-%m-%d %H:%M")
    except (OSError, ValueError):
        return "N/A"


def truncate(text: str, max_len: int) -> str:
    """截断文本。"""
    text = text.replace("\n", " ").strip()
    return text[: max_len - 3] + "..." if len(text) > max_len else text


# ---------------------------------------------------------------------------
# 过滤器
# ---------------------------------------------------------------------------


def filter_by_time(
    groups: dict[str, list[dict]],
    days: int | None = None,
    after: str | None = None,
    before: str | None = None,
) -> dict[str, list[dict]]:
    """按时间过滤会话组。"""
    now_ms = datetime.now().timestamp() * 1000

    if days is not None:
        cutoff_ms = now_ms - days * 86400 * 1000
    elif after is not None:
        cutoff_ms = datetime.strptime(after, "%Y-%m-%d").timestamp() * 1000
    else:
        cutoff_ms = 0

    end_ms = (
        datetime.strptime(before, "%Y-%m-%d").timestamp() * 1000
        if before is not None
        else float("inf")
    )

    return {
        sid: recs
        for sid, recs in groups.items()
        if cutoff_ms <= max(r.get("timestamp", 0) for r in recs) <= end_ms
    }


def filter_by_project(
    groups: dict[str, list[dict]], project_keyword: str
) -> dict[str, list[dict]]:
    """按项目路径关键词过滤。"""
    filtered = {}
    for sid, recs in groups.items():
        for r in recs:
            if project_keyword.lower() in r.get("project", "").lower():
                filtered[sid] = recs
                break
    return filtered


# ---------------------------------------------------------------------------
# 搜索引擎: 关键词
# ---------------------------------------------------------------------------


def search_keyword(
    groups: dict[str, list[dict]], keywords: list[str]
) -> list[dict]:
    """关键词搜索 (正则 OR 匹配)。"""
    results = []
    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)

    for sid, recs in groups.items():
        hits = 0
        matched_texts = []
        for r in recs:
            display = r.get("display", "")
            matches = pattern.findall(display)
            if matches:
                hits += len(matches)
                matched_texts.append(display)

        if hits > 0:
            sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))
            results.append({
                "session_id": sid,
                "hits": hits,
                "first_msg": get_first_user_input(recs),
                "user_inputs": get_user_inputs(recs),
                "last_time": sorted_recs[-1].get("timestamp", 0),
                "project": sorted_recs[0].get("project", ""),
                "matched_texts": matched_texts,
                "total_messages": len(recs),
            })

    results.sort(key=lambda x: (-x["hits"], -x["last_time"]))
    return results


# ---------------------------------------------------------------------------
# 搜索引擎: 深度搜索
# ---------------------------------------------------------------------------


def deep_search(
    projects_dir: str, keywords: list[str], groups: dict[str, list[dict]]
) -> list[dict]:
    """深度搜索：扫描项目目录下完整对话 JSONL。"""
    proj_path = Path(projects_dir).expanduser()
    if not proj_path.exists():
        print(f"⚠️  项目目录不存在: {proj_path}", file=sys.stderr)
        return []

    pattern = re.compile("|".join(re.escape(k) for k in keywords), re.IGNORECASE)
    results_map: dict[str, dict] = {}

    for project_dir in proj_path.iterdir():
        if not project_dir.is_dir():
            continue
        for jsonl_file in project_dir.glob("*.jsonl"):
            if not jsonl_file.is_file():
                continue
            sid = jsonl_file.stem
            try:
                content = jsonl_file.read_text(encoding="utf-8", errors="ignore")
                matches = pattern.findall(content)
                if matches:
                    mtime = jsonl_file.stat().st_mtime * 1000
                    first_msg = ""
                    if sid in groups and groups[sid]:
                        first_msg = get_first_user_input(groups[sid])

                    if sid not in results_map or len(matches) > results_map[sid]["hits"]:
                        user_inputs = []
                        if sid in groups and groups[sid]:
                            user_inputs = get_user_inputs(groups[sid])
                        results_map[sid] = {
                            "session_id": sid,
                            "hits": len(matches),
                            "first_msg": first_msg or f"[{jsonl_file.name}]",
                            "user_inputs": user_inputs,
                            "last_time": mtime,
                            "project": str(project_dir.name),
                            "matched_texts": matches[:5],
                            "total_messages": 0,
                            "file_size": jsonl_file.stat().st_size,
                        }
            except Exception:
                continue

    results = list(results_map.values())
    results.sort(key=lambda x: (-x["hits"], -x["last_time"]))
    return results


# ---------------------------------------------------------------------------
# AI 语义搜索: Embedding 向量索引
# ---------------------------------------------------------------------------


class EmbeddingIndex:
    """会话向量索引 — 支持持久化缓存，增量更新。"""

    def __init__(self, config: dict):
        self.cfg = config["embedding"]
        self.api_key = os.environ.get("ARK_API_KEY")
        self.index_path = INDEX_DIR / "session_embeddings.json"
        self._client = None
        self._cache: dict[str, list[float]] = {}  # session_id -> embedding
        self._cache_meta: dict[str, str] = {}      # session_id -> content_hash
        self._load_cache()

    @property
    def client(self):
        if self._client is None:
            from volcenginesdkarkruntime import Ark
            self._client = Ark(api_key=self.api_key)
        return self._client

    def _load_cache(self):
        """从磁盘加载已缓存的向量。"""
        if self.index_path.exists():
            try:
                data = json.loads(self.index_path.read_text(encoding="utf-8"))
                self._cache = data.get("embeddings", {})
                self._cache_meta = data.get("meta", {})
            except Exception:
                self._cache = {}
                self._cache_meta = {}

    def _save_cache(self):
        """将向量缓存持久化到磁盘。"""
        INDEX_DIR.mkdir(parents=True, exist_ok=True)
        data = {
            "embeddings": self._cache,
            "meta": self._cache_meta,
            "updated_at": datetime.now().isoformat(),
        }
        self.index_path.write_text(
            json.dumps(data, ensure_ascii=False), encoding="utf-8"
        )

    @staticmethod
    def _content_hash(text: str) -> str:
        """计算内容哈希，用于判断是否需要重新嵌入。"""
        return hashlib.md5(text.encode("utf-8")).hexdigest()[:12]

    def _embed_batch(self, texts: list[str]) -> list[list[float]]:
        """批量调用火山方舟 Multimodal Embedding API。"""
        results = []
        for text in texts:
            truncated = text[:4000]
            response = self.client.multimodal_embeddings.create(
                model=self.cfg["model"],
                input=[{"type": "text", "text": truncated}],
            )
            # response.data 是单个 MultimodalEmbedding 对象，非列表
            results.append(response.data.embedding)
        return results

    def build_index(self, groups: dict[str, list[dict]]) -> int:
        """构建/增量更新向量索引。返回新嵌入的会话数。"""
        to_embed: list[tuple[str, str]] = []  # (session_id, text)

        for sid, recs in groups.items():
            text = get_session_text(recs)
            if not text.strip():
                continue
            content_hash = self._content_hash(text)
            # 跳过已缓存且内容未变的
            if sid in self._cache and self._cache_meta.get(sid) == content_hash:
                continue
            self._cache_meta[sid] = content_hash
            to_embed.append((sid, text))

        if not to_embed:
            return 0

        batch_size = self.cfg.get("batch_size", 20)
        new_count = 0
        total = len(to_embed)

        for i in range(0, total, batch_size):
            batch = to_embed[i : i + batch_size]
            sids = [item[0] for item in batch]
            texts = [item[1] for item in batch]
            try:
                embeddings = self._embed_batch(texts)
                for sid, emb in zip(sids, embeddings):
                    self._cache[sid] = emb
                new_count += len(batch)
                print(
                    f"  📊 嵌入进度: {min(i + batch_size, total)}/{total}",
                    end="\r",
                    flush=True,
                )
            except Exception as e:
                print(f"\n  ⚠️  嵌入批次失败 ({i}-{i+batch_size}): {e}", file=sys.stderr)
                continue

        if new_count > 0:
            print()  # 换行
            self._save_cache()

        return new_count

    def search(
        self, query: str, groups: dict[str, list[dict]], top_k: int | None = None
    ) -> list[tuple[str, float]]:
        """
        向量相似度搜索。
        返回: [(session_id, similarity_score), ...] 按相似度降序。
        """
        import numpy as np

        top_k = top_k or self.cfg.get("top_k", 30)
        threshold = self.cfg.get("similarity_threshold", 0.3)

        # 嵌入 query
        query_emb = self._embed_batch([query])[0]
        query_vec = np.array(query_emb, dtype=np.float32)
        query_norm = np.linalg.norm(query_vec)
        if query_norm == 0:
            return []

        # 计算余弦相似度
        scores: list[tuple[str, float]] = []
        for sid, emb in self._cache.items():
            if sid not in groups:
                continue
            doc_vec = np.array(emb, dtype=np.float32)
            doc_norm = np.linalg.norm(doc_vec)
            if doc_norm == 0:
                continue
            similarity = float(np.dot(query_vec, doc_vec) / (query_norm * doc_norm))
            if similarity >= threshold:
                scores.append((sid, similarity))

        scores.sort(key=lambda x: -x[1])
        return scores[:top_k]


# ---------------------------------------------------------------------------
# AI 语义搜索: LLM Rerank + 摘要
# ---------------------------------------------------------------------------


def llm_rerank(
    candidates: list[dict], query: str, config: dict
) -> list[dict]:
    """调用 GLM-4-7 对候选结果做精排 + 摘要生成。"""
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        return candidates

    try:
        from volcenginesdkarkruntime import Ark
    except ImportError:
        print("⚠️  未安装 volcenginesdkarkruntime (pip install 'volcengine-python-sdk[ark]')", file=sys.stderr)
        return candidates

    rerank_cfg = config["rerank"]
    client = Ark(api_key=api_key)
    max_candidates = rerank_cfg.get("max_candidates", 15)

    sessions_text = []
    for i, r in enumerate(candidates[:max_candidates]):
        msgs = "\n".join(r.get("matched_texts", [])[:3])
        sessions_text.append(
            f"[{i+1}] Session: {r['session_id']}\n"
            f"    首条消息: {r['first_msg'][:100]}\n"
            f"    匹配文本: {msgs[:300]}\n"
            f"    相似度: {r.get('similarity', 'N/A')}"
        )

    prompt = f"""用户正在搜索 Claude Code 的历史对话记录。

搜索查询: "{query}"

以下是通过语义召回找到的候选会话:

{chr(10).join(sessions_text)}

请完成以下任务:
1. 根据用户搜索意图，按相关性重新排序（最相关的排最前）
2. 为每个会话生成一句话中文摘要（不超过 30 字）
3. 对明显不相关的会话标记 relevant=false

以 JSON 格式返回:
```json
{{
  "ranked": [
    {{"index": 1, "summary": "一句话摘要", "relevant": true}},
    ...
  ]
}}
```

只返回 JSON。"""

    try:
        response = client.chat.completions.create(
            model=rerank_cfg["model"],
            messages=[{"role": "user", "content": prompt}],
            temperature=rerank_cfg.get("temperature", 0.3),
            timeout=rerank_cfg.get("timeout", 30),
        )
        content = response.choices[0].message.content.strip()
        json_match = re.search(r"\{[\s\S]*\}", content)
        if json_match:
            data = json.loads(json_match.group())
            ranked = data.get("ranked", [])

            reordered = []
            for item in ranked:
                idx = item.get("index", 0) - 1
                if 0 <= idx < len(candidates):
                    if item.get("relevant", True):
                        candidates[idx]["ai_summary"] = item.get("summary", "")
                        reordered.append(candidates[idx])

            # 补充未被 LLM 处理到的结果
            ranked_ids = {r["session_id"] for r in reordered}
            for r in candidates:
                if r["session_id"] not in ranked_ids:
                    reordered.append(r)

            return reordered
    except Exception as e:
        print(f"⚠️  LLM 精排失败: {e}", file=sys.stderr)

    return candidates


# ---------------------------------------------------------------------------
# AI 语义搜索: 主流程
# ---------------------------------------------------------------------------


def ai_semantic_search(
    query: str, groups: dict[str, list[dict]], config: dict
) -> list[dict]:
    """
    两阶段语义搜索:
      Stage 1: Embedding 向量召回 → Top-K 候选
      Stage 2: GLM-4-7 精排 + 摘要生成
    """
    api_key = os.environ.get("ARK_API_KEY")
    if not api_key:
        print("❌ 未设置 ARK_API_KEY 环境变量，无法使用 AI 语义搜索", file=sys.stderr)
        return []

    try:
        import numpy as np
        from volcenginesdkarkruntime import Ark
    except ImportError as e:
        print(f"❌ 缺少依赖: {e}\n   pip install 'volcengine-python-sdk[ark]' numpy", file=sys.stderr)
        return []

    # --- Stage 1: Embedding 向量召回 ---
    print("🔢 Stage 1: Embedding 向量召回...")
    index = EmbeddingIndex(config)

    # 构建/更新索引
    new_count = index.build_index(groups)
    cached_count = len(index._cache)
    if new_count > 0:
        print(f"  ✅ 新嵌入 {new_count} 个会话，索引总量: {cached_count}")
    else:
        print(f"  ✅ 使用缓存索引（{cached_count} 个会话）")

    # 向量搜索
    search_results = index.search(query, groups)
    if not search_results:
        print("  ⚠️  未找到语义匹配的会话")
        return []

    print(f"  📋 召回 {len(search_results)} 个候选（相似度 {search_results[0][1]:.3f} ~ {search_results[-1][1]:.3f}）")

    # 构建候选列表
    candidates = []
    for sid, score in search_results:
        recs = groups[sid]
        sorted_recs = sorted(recs, key=lambda x: x.get("timestamp", 0))

        # 收集匹配文本
        all_texts = [r.get("display", "") for r in recs if r.get("display", "").strip()]

        candidates.append({
            "session_id": sid,
            "similarity": round(score, 4),
            "hits": 0,  # 语义搜索不计关键词命中
            "first_msg": get_first_user_input(recs),
            "user_inputs": get_user_inputs(recs),
            "last_time": sorted_recs[-1].get("timestamp", 0),
            "project": sorted_recs[0].get("project", ""),
            "matched_texts": all_texts[:5],
            "total_messages": len(recs),
        })

    # --- Stage 2: LLM Rerank + 摘要 ---
    print("🤖 Stage 2: GLM-4-7 精排 + 摘要生成...")
    results = llm_rerank(candidates, query, config)
    print(f"  ✅ 精排完成，{len(results)} 个结果")

    return results


# ---------------------------------------------------------------------------
# 输出格式化
# ---------------------------------------------------------------------------


def print_results(
    results: list[dict],
    query: str,
    limit: int,
    max_display_length: int,
    verbose: bool = False,
    is_semantic: bool = False,
):
    """卡片式格式化输出搜索结果。"""
    total = len(results)
    results = results[:limit]

    if not results:
        print(f"\n🔍 搜索 \"{query}\" — 未找到匹配会话\n")
        return

    mode = "语义" if is_semantic else "关键词"
    print(f"\n{'━' * 80}")
    print(f"  🔍 搜索 \"{query}\" ({mode}) — 找到 {total} 个匹配会话", end="")
    if total > limit:
        print(f"，显示前 {limit} 条")
    else:
        print()
    print(f"{'━' * 80}")

    for i, r in enumerate(results, 1):
        sid = r["session_id"]
        time_str = format_timestamp(r["last_time"])
        ai_summary = r.get("ai_summary", "")
        user_inputs = r.get("user_inputs", [])
        total_msgs = r.get("total_messages", 0)

        if is_semantic:
            score_str = f"相似度 {r.get('similarity', 0):.3f}"
        else:
            score_str = f"命中 {r['hits']} 次"

        # 卡片头部
        print(f"\n  ┌─ #{i}  {time_str}  {score_str}  共 {total_msgs} 条消息")
        print(f"  │  📎 {sid}")

        if ai_summary:
            print(f"  │  📝 {ai_summary}")

        # 用户输入列表
        display_inputs = user_inputs[:4] if not verbose else user_inputs[:6]
        remaining = len(user_inputs) - len(display_inputs)

        for j, ui in enumerate(display_inputs):
            is_last = (j == len(display_inputs) - 1) and remaining <= 0
            prefix = "└─" if is_last else "├─"
            print(f"  │  {prefix} 💬 {truncate(ui, max_display_length)}")

        if remaining > 0:
            print(f"  │  └─ ... 还有 {remaining} 条输入")

        print(f"  └{'─' * 79}")

    # 恢复命令
    print(f"\n{'━' * 80}")
    print("  📋 恢复命令:\n")
    for i, r in enumerate(results[:5], 1):
        print(f"  {i}. claude --resume {r['session_id']}")
    if len(results) > 5:
        print(f"\n  ... 还有 {len(results) - 5} 条")
    print(f"\n{'━' * 80}\n")


# ---------------------------------------------------------------------------
# 主入口
# ---------------------------------------------------------------------------


def main():
    parser = argparse.ArgumentParser(
        description="🔍 Claude Code 历史会话搜索工具",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  %(prog)s "jmf 端口"            # 关键词搜索
  %(prog)s "summarize" -d 7      # 最近 7 天
  %(prog)s "端口转发" --deep      # 深度搜索完整对话
  %(prog)s "如何配置远程转发" --ai # AI 语义搜索（两阶段）
  %(prog)s "ssh" -p farbay       # 按项目过滤
  %(prog)s --rebuild-index       # 强制重建向量索引
        """,
    )
    parser.add_argument("query", nargs="?", default=None, help="搜索关键词")
    parser.add_argument(
        "-n", "--limit", type=int, default=None, help="最多显示条数 (默认 20)"
    )
    parser.add_argument("-d", "--days", type=int, help="只搜索最近 N 天")
    parser.add_argument("--after", help="搜索指定日期之后 (YYYY-MM-DD)")
    parser.add_argument("--before", help="搜索指定日期之前 (YYYY-MM-DD)")
    parser.add_argument("-p", "--project", help="按项目路径关键词过滤")
    parser.add_argument(
        "--deep", action="store_true", help="深度搜索（搜索完整对话 JSONL 文件）"
    )
    parser.add_argument(
        "--ai", action="store_true",
        help="AI 语义搜索: Embedding 召回 + GLM-4-7 精排 (需要 ARK_API_KEY)",
    )
    parser.add_argument(
        "--rebuild-index", action="store_true", help="强制重建向量索引"
    )
    parser.add_argument("--no-proxy", action="store_true", help="清除代理设置")
    parser.add_argument(
        "-v", "--verbose", action="store_true", help="显示更多匹配上下文"
    )
    args = parser.parse_args()

    # 清除代理
    if args.no_proxy:
        for key in ["http_proxy", "https_proxy", "HTTP_PROXY", "HTTPS_PROXY", "ALL_PROXY", "all_proxy"]:
            os.environ.pop(key, None)

    # 加载配置
    config = load_config()
    limit = args.limit or config["search"]["default_limit"]
    max_display_length = config["search"]["max_display_length"]

    # 加载历史
    history_file = config["paths"]["history_file"]
    records = parse_history(history_file)
    print(f"📂 已加载 {len(records)} 条历史记录")

    groups = group_by_session(records)
    print(f"📦 共 {len(groups)} 个会话")

    # 应用过滤器
    if args.days or args.after or args.before:
        groups = filter_by_time(groups, args.days, args.after, args.before)
        print(f"⏰ 时间过滤后: {len(groups)} 个会话")

    if args.project:
        groups = filter_by_project(groups, args.project)
        print(f"📁 项目过滤后: {len(groups)} 个会话")

    # 强制重建索引
    if args.rebuild_index:
        print("🔄 强制重建向量索引...")
        idx_file = INDEX_DIR / "session_embeddings.json"
        if idx_file.exists():
            idx_file.unlink()
            print("  🗑️  已清除旧索引")
        if not args.query:
            index = EmbeddingIndex(config)
            new_count = index.build_index(groups)
            print(f"  ✅ 索引构建完成，共嵌入 {new_count} 个会话")
            return

    if not args.query:
        parser.print_help()
        return

    keywords = args.query.split()

    # 搜索
    if args.ai:
        # AI 两阶段语义搜索
        results = ai_semantic_search(args.query, groups, config)
        print_results(results, args.query, limit, max_display_length, args.verbose, is_semantic=True)
    elif args.deep:
        print("🔎 深度搜索中（扫描完整对话文件）...")
        results = deep_search(config["paths"]["projects_dir"], keywords, groups)
        print_results(results, args.query, limit, max_display_length, args.verbose)
    else:
        results = search_keyword(groups, keywords)
        print_results(results, args.query, limit, max_display_length, args.verbose)


if __name__ == "__main__":
    main()

"""Three-tier session memory extension: L1 runtime pins, L2 SQLite TTL/FTS5, L3 Markdown."""

from datetime import datetime, timedelta, timezone
from pathlib import Path
import re
import sqlite3
from typing import Protocol
import uuid

from .extensions import ExtensionAPI
from .tools import Tool, ToolError, integer, parameters, string

LONG_CATEGORIES = ("user", "feedback", "project", "reference")
ENTRY_HEADER = re.compile(r"^## \[([^\]]+)\]\s*(.+?)\s*$")


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _fts_query(query: str) -> str:
    tokens = re.findall(r"[0-9A-Za-z_\u4e00-\u9fff]{2,}", query)
    if not tokens:
        return ""
    return " OR ".join(f'"{tok}"' for tok in tokens[:8])


class MemoryBackend(Protocol):
    def pin(self, session_id: str, content: str) -> dict: ...
    def unpin(self, session_id: str, pin_id: int) -> bool: ...
    def list_pins(self, session_id: str) -> list[dict]: ...
    def save_short(self, content: str, *, source_session: str | None = None,
                   ttl_days: int = 7, tags: tuple[str, ...] = ()) -> dict: ...
    def search_short(self, query: str, *, limit: int = 5) -> list[dict]: ...
    def list_short(self, limit: int = 10) -> list[dict]: ...
    def delete_short(self, item_id: str) -> bool: ...
    def save_long(self, category: str, title: str, content: str) -> dict: ...
    def search_long(self, query: str, *, limit: int = 5) -> list[dict]: ...
    def list_long(self) -> list[dict]: ...
    def delete_long(self, item_id: str) -> bool: ...


class LocalMemoryStore:
    """Zero-dependency local backend: SQLite (L1/L2 + FTS5) and editable Markdown files (L3)."""

    def __init__(self, root: Path, *, now_fn=_utc_now):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.now_fn = now_fn
        self.db_path = self.root / "memory.sqlite3"
        self.db = sqlite3.connect(self.db_path)
        self.db.row_factory = sqlite3.Row
        self._has_fts = False
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS session_pins (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                session_id TEXT NOT NULL,
                content TEXT NOT NULL,
                created_at TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS idx_pins_session ON session_pins(session_id, id);
            CREATE TABLE IF NOT EXISTS short_memories (
                id TEXT PRIMARY KEY,
                content TEXT NOT NULL,
                tags TEXT NOT NULL,
                source_session TEXT,
                created_at TEXT NOT NULL,
                expires_at TEXT NOT NULL,
                hits INTEGER NOT NULL DEFAULT 0
            );
            CREATE INDEX IF NOT EXISTS idx_short_expires ON short_memories(expires_at);
        """)
        try:
            self.db.execute(
                "CREATE VIRTUAL TABLE IF NOT EXISTS short_memories_fts "
                "USING fts5(id UNINDEXED, content, tags)")
            self._has_fts = True
        except sqlite3.OperationalError:
            self._has_fts = False

    def close(self):
        self.db.close()

    # ---------- L1: Runtime Session Pins ----------

    def pin(self, session_id: str, content: str) -> dict:
        text = content.strip()
        if not text:
            raise ValueError("置顶要求不能为空")
        stamp = self.now_fn().isoformat()
        with self.db:
            cur = self.db.execute(
                "INSERT INTO session_pins(session_id, content, created_at) VALUES (?,?,?)",
                (session_id, text, stamp))
        return {"id": cur.lastrowid, "session_id": session_id, "content": text, "created_at": stamp}

    def unpin(self, session_id: str, pin_id: int) -> bool:
        with self.db:
            cur = self.db.execute(
                "DELETE FROM session_pins WHERE session_id=? AND id=?", (session_id, pin_id))
        return cur.rowcount > 0

    def list_pins(self, session_id: str) -> list[dict]:
        rows = self.db.execute(
            "SELECT id, session_id, content, created_at FROM session_pins WHERE session_id=? ORDER BY id",
            (session_id,)).fetchall()
        return [dict(r) for r in rows]

    # ---------- L2: Short-term Cross-Session Memory (TTL + FTS5) ----------

    def prune_expired(self) -> int:
        now_iso = self.now_fn().isoformat()
        expired = [r["id"] for r in self.db.execute(
            "SELECT id FROM short_memories WHERE expires_at <= ?", (now_iso,))]
        if not expired:
            return 0
        with self.db:
            self.db.executemany("DELETE FROM short_memories WHERE id=?", ((i,) for i in expired))
            if self._has_fts:
                self.db.executemany("DELETE FROM short_memories_fts WHERE id=?", ((i,) for i in expired))
        return len(expired)

    def save_short(self, content: str, *, source_session: str | None = None,
                   ttl_days: int = 7, tags: tuple[str, ...] = ()) -> dict:
        text = content.strip()
        if not text:
            raise ValueError("短期记忆内容不能为空")
        if ttl_days < 1 or ttl_days > 365:
            raise ValueError("ttl_days 应在 1 到 365 之间")
        self.prune_expired()
        now = self.now_fn()
        item_id = "sm_" + uuid.uuid4().hex[:8]
        tag_text = " ".join(t.strip() for t in tags if t.strip())
        created = now.isoformat()
        expires = (now + timedelta(days=ttl_days)).isoformat()
        with self.db:
            self.db.execute(
                "INSERT INTO short_memories(id, content, tags, source_session, created_at, expires_at, hits) "
                "VALUES (?,?,?,?,?,?,0)",
                (item_id, text, tag_text, source_session, created, expires))
            if self._has_fts:
                self.db.execute(
                    "INSERT INTO short_memories_fts(id, content, tags) VALUES (?,?,?)",
                    (item_id, text, tag_text))
        return {"id": item_id, "content": text, "tags": tag_text, "source_session": source_session,
                "created_at": created, "expires_at": expires}

    def list_short(self, limit: int = 10) -> list[dict]:
        self.prune_expired()
        rows = self.db.execute(
            "SELECT id, content, tags, source_session, created_at, expires_at, hits "
            "FROM short_memories ORDER BY created_at DESC LIMIT ?", (limit,)).fetchall()
        return [dict(r) for r in rows]

    def search_short(self, query: str, *, limit: int = 5) -> list[dict]:
        self.prune_expired()
        text = query.strip()
        if not text:
            return self.list_short(limit=limit)
        rows = []
        if self._has_fts:
            fts = _fts_query(text)
            if fts:
                try:
                    rows = self.db.execute(
                        "SELECT s.id, s.content, s.tags, s.source_session, s.created_at, s.expires_at, s.hits "
                        "FROM short_memories_fts f JOIN short_memories s ON f.id = s.id "
                        "WHERE short_memories_fts MATCH ? ORDER BY bm25(short_memories_fts), s.created_at DESC LIMIT ?",
                        (fts, limit)).fetchall()
                except sqlite3.OperationalError:
                    rows = []
        if not rows:
            terms = [tok.casefold() for tok in re.findall(r"[0-9A-Za-z_\u4e00-\u9fff]{2,}", text)[:6]]
            all_rows = self.db.execute(
                "SELECT id, content, tags, source_session, created_at, expires_at, hits "
                "FROM short_memories ORDER BY created_at DESC LIMIT 200").fetchall()
            scored = []
            for r in all_rows:
                hay = (r["content"] + " " + r["tags"]).casefold()
                score = sum(1 for tok in terms if tok in hay) if terms else (1 if text.casefold() in hay else 0)
                if score:
                    scored.append((score, r["created_at"], r))
            scored.sort(key=lambda item: (item[0], item[1]), reverse=True)
            rows = [item[2] for item in scored[:limit]]
        if rows:
            with self.db:
                self.db.executemany("UPDATE short_memories SET hits=hits+1 WHERE id=?", ((r["id"],) for r in rows))
        return [dict(r) for r in rows]

    def delete_short(self, item_id: str) -> bool:
        with self.db:
            cur = self.db.execute("DELETE FROM short_memories WHERE id=?", (item_id,))
            if self._has_fts:
                self.db.execute("DELETE FROM short_memories_fts WHERE id=?", (item_id,))
        return cur.rowcount > 0

    # ---------- L3: Long-term Markdown Memory (Claude Code style) ----------

    def _category_path(self, category: str) -> Path:
        if category not in LONG_CATEGORIES:
            raise ValueError(f"长期记忆分类必须是：{', '.join(LONG_CATEGORIES)}")
        return self.root / f"{category}.md"

    def _parse_category_file(self, category: str) -> list[dict]:
        path = self._category_path(category)
        if not path.is_file():
            return []
        entries: list[dict] = []
        current: dict | None = None
        body_lines: list[str] = []

        def flush():
            if current is not None:
                current["content"] = "\n".join(body_lines).strip()
                entries.append(current)

        for line in path.read_text(encoding="utf-8-sig").splitlines():
            match = ENTRY_HEADER.match(line)
            if match:
                flush()
                current = {"id": match.group(1), "category": category, "title": match.group(2),
                           "file": path.name, "content": ""}
                body_lines = []
            elif current is not None:
                body_lines.append(line)
        flush()
        return entries

    def _write_category_file(self, category: str, entries: list[dict]):
        path = self._category_path(category)
        if not entries:
            if path.exists():
                path.unlink()
            return
        chunks = [f"# {category} memory\n"]
        for entry in entries:
            chunks.append(f"## [{entry['id']}] {entry['title']}\n{entry['content']}\n")
        path.write_text("\n".join(chunks), encoding="utf-8")

    def _rebuild_index(self):
        entries = self.list_long()
        index_path = self.root / "MEMORY.md"
        lines = ["# Long-Term Memory Index", ""]
        for entry in entries:
            lines.append(f"- [{entry['id']}] ({entry['category']}) {entry['title']} -> `{entry['file']}`")
        index_path.write_text("\n".join(lines) + "\n", encoding="utf-8")

    def save_long(self, category: str, title: str, content: str) -> dict:
        clean_title = title.strip().replace("\n", " ")[:120]
        clean_content = content.strip()
        if not clean_title or not clean_content:
            raise ValueError("长期记忆标题和内容不能为空")
        entries = self._parse_category_file(category)
        entry = {"id": "lm_" + uuid.uuid4().hex[:8], "category": category,
                 "title": clean_title, "file": f"{category}.md", "content": clean_content}
        entries.append(entry)
        self._write_category_file(category, entries)
        self._rebuild_index()
        return entry

    def list_long(self) -> list[dict]:
        all_entries: list[dict] = []
        for category in LONG_CATEGORIES:
            all_entries.extend(self._parse_category_file(category))
        return all_entries

    def search_long(self, query: str, *, limit: int = 5) -> list[dict]:
        entries = self.list_long()
        text = query.strip()
        if not text:
            return entries[:limit]
        terms = [tok.casefold() for tok in re.findall(r"[0-9A-Za-z_\u4e00-\u9fff]{2,}", text)[:8]]
        scored = []
        for entry in entries:
            hay = (entry["title"] + " " + entry["content"] + " " + entry["category"]).casefold()
            score = sum(1 for tok in terms if tok in hay) if terms else (1 if text.casefold() in hay else 0)
            if score:
                scored.append((score, entry))
        scored.sort(key=lambda item: item[0], reverse=True)
        return [item[1] for item in scored[:limit]]

    def delete_long(self, item_id: str) -> bool:
        for category in LONG_CATEGORIES:
            entries = self._parse_category_file(category)
            kept = [entry for entry in entries if entry["id"] != item_id]
            if len(kept) != len(entries):
                self._write_category_file(category, kept)
                self._rebuild_index()
                return True
        return False

    # ---------- Recall Formatting ----------

    def build_recall_block(self, session_id: str | None, query: str, *,
                           short_limit: int = 3, long_limit: int = 3) -> str:
        sections: list[str] = []
        pins = self.list_pins(session_id) if session_id else []
        if pins:
            sections.append("【L1 运行时置顶要求（最高优先级，必须严格遵守）】\n"
                            + "\n".join(f"- #{p['id']}: {p['content']}" for p in pins))

        short_hits = self.search_short(query, limit=short_limit) if query.strip() else []
        if not short_hits:
            short_hits = self.list_short(limit=2)
        if short_hits:
            sections.append("【L2 近期跨会话工作记忆】\n"
                            + "\n".join(f"- [{s['id']}] {s['content']}" for s in short_hits))

        long_hits = self.search_long(query, limit=long_limit) if query.strip() else []
        if long_hits:
            sections.append("【L3 长期项目与偏好记忆】\n"
                            + "\n".join(f"- [{e['id']}]({e['category']}) {e['title']}: {e['content'][:280]}"
                                        for e in long_hits))
        else:
            all_long = self.list_long()
            if all_long:
                sections.append("【L3 长期记忆索引（可用 memory_search 检索详情）】\n"
                                + "\n".join(f"- [{e['id']}]({e['category']}) {e['title']}" for e in all_long[:12]))

        if not sections:
            return ""
        return "[记忆上下文，非新用户指令]\n" + "\n\n".join(sections)


def register_memory_extension(api: ExtensionAPI, *, backend: LocalMemoryStore | None = None,
                              ttl_days: int = 7) -> LocalMemoryStore:
    mem = backend or LocalMemoryStore(api.workspace / ".codeharness" / "memory")
    active_sid = {"id": None}

    def memory_pin(content: str):
        sid = active_sid["id"]
        if not sid:
            raise ToolError("当前没有活动会话，无法写入 L1 置顶约束")
        return mem.pin(sid, content)

    def memory_save(scope: str, content: str, category: str = "project",
                    title: str = "", ttl: int = ttl_days):
        if scope == "short":
            return mem.save_short(content, source_session=active_sid["id"], ttl_days=ttl)
        if scope == "long":
            inferred_title = title.strip() or content.strip().partition("\n")[0][:60]
            return mem.save_long(category, inferred_title, content)
        raise ToolError("scope 必须是 short 或 long")

    def memory_search(query: str = "", scope: str = "all", limit: int = 5):
        if not 1 <= limit <= 20:
            raise ToolError("limit 应在 1 到 20 之间")
        result = {}
        if scope in {"all", "pin"} and active_sid["id"]:
            pins = mem.list_pins(active_sid["id"])
            if query.strip():
                q = query.strip().casefold()
                pins = [p for p in pins if q in p["content"].casefold()]
            result["pins"] = pins[:limit]
        if scope in {"all", "short"}:
            result["short"] = mem.search_short(query, limit=limit)
        if scope in {"all", "long"}:
            result["long"] = mem.search_long(query, limit=limit)
        return result

    def memory_forget(scope: str, item_id: str):
        if scope == "pin":
            if not active_sid["id"]:
                raise ToolError("当前没有活动会话")
            try:
                pid = int(item_id)
            except ValueError:
                raise ToolError("L1 pin 的 item_id 必须是数字") from None
            return {"deleted": mem.unpin(active_sid["id"], pid)}
        if scope == "short":
            return {"deleted": mem.delete_short(item_id)}
        if scope == "long":
            return {"deleted": mem.delete_long(item_id)}
        raise ToolError("scope 必须是 pin、short 或 long")

    api.register_tool(Tool(
        "memory_pin", "将用户在本会话中明确提出的高优先级约束置顶（L1，永不被压缩）。",
        parameters({"content": string("要置顶的硬性要求或约束")}, ["content"]), memory_pin, "write"))
    api.register_tool(Tool(
        "memory_save", "保存跨会话记忆：short 写入带 TTL 的 SQLite 短期记忆（L2），long 写入人类可读的 Markdown 长期记忆（L3）。",
        parameters({
            "scope": {"type": "string", "enum": ["short", "long"], "description": "记忆层级"},
            "content": string("记忆正文"),
            "category": {"type": "string", "enum": list(LONG_CATEGORIES), "description": "长期记忆分类（仅 long）"},
            "title": string("长期记忆简短标题（仅 long）"),
            "ttl": integer("短期记忆有效天数，默认 7（仅 short）"),
        }, ["scope", "content"]), memory_save, "write"))
    api.register_tool(Tool(
        "memory_search", "跨 L1 置顶 / L2 短期 / L3 长期记忆检索相关信息。",
        parameters({
            "query": string("检索关键词，空则返回近期条目"),
            "scope": {"type": "string", "enum": ["all", "pin", "short", "long"], "description": "检索范围"},
            "limit": integer("每层返回上限，默认 5"),
        }), memory_search, "read"))
    api.register_tool(Tool(
        "memory_forget", "删除一条过期或错误的记忆。",
        parameters({
            "scope": {"type": "string", "enum": ["pin", "short", "long"], "description": "记忆层级"},
            "item_id": string("记忆 ID"),
        }, ["scope", "item_id"]), memory_forget, "write"))

    def on_session_start(event: dict):
        active_sid["id"] = event["session_id"]

    def on_before_context(event: dict):
        sid = event["session_id"]
        active_sid["id"] = sid
        messages = event["messages"]
        last_user = next((m.get("content", "") for m in reversed(messages)
                          if m.get("role") == "user" and not str(m.get("content", "")).startswith("[")), "")
        block = mem.build_recall_block(sid, str(last_user))
        if not block:
            return None
        # Insert before the latest user message so messages[0] (system) stays stable for prefix caching.
        insert_at = next((i for i in range(len(messages) - 1, 0, -1) if messages[i].get("role") == "user"), len(messages))
        return {"insert_at": insert_at, "message": {"role": "user", "content": block}}

    def on_session_end(event: dict):
        result = event["result"]
        if result.status not in {"completed", "verified", "unverified"}:
            return
        if not result.changed_files:
            return
        task = str(event.get("task", "")).strip()[:120]
        summary = f"任务「{task}」改动了 {', '.join(result.changed_files[:6])}（状态：{result.status}）。"
        existing = mem.list_short(limit=3)
        if any(item["content"] == summary for item in existing):
            return
        mem.save_short(summary, source_session=result.session_id, ttl_days=ttl_days,
                       tags=tuple(result.changed_files[:4]))

    api.on("session_start", on_session_start)
    api.on("before_context", on_before_context)
    api.on("session_end", on_session_end)

    # ---------- Interactive Slash Commands ----------

    def cmd_memory(args: str, ctx: dict):
        sid = ctx.get("session_id")
        pins = mem.list_pins(sid) if sid else []
        shorts = mem.list_short(limit=8)
        longs = mem.list_long()
        lines = ["=== 三层记忆总览 ==="]
        lines.append(f"[L1 本会话置顶 ({len(pins)})]")
        lines.extend([f"  #{p['id']}: {p['content']}" for p in pins] or ["  （无）"])
        lines.append(f"[L2 短期跨会话 ({len(shorts)})]")
        lines.extend([f"  [{s['id']}] {s['content']} (到期 {s['expires_at'][:10]})" for s in shorts] or ["  （无）"])
        lines.append(f"[L3 长期 Markdown ({len(longs)}) -> {mem.root}]")
        lines.extend([f"  [{e['id']}] ({e['category']}) {e['title']}" for e in longs] or ["  （无）"])
        return "\n".join(lines)

    def cmd_pin(args: str, ctx: dict):
        sid = ctx.get("session_id")
        text = args.strip()
        if not text:
            return "用法：/pin <本会话必须遵守的硬要求> 或 /pin del <ID>"
        if not sid:
            return "请先发送第一条消息建立会话后再 /pin（或直接告诉模型调用 memory_pin）。"
        if text.startswith("del "):
            try:
                pid = int(text[4:].strip())
            except ValueError:
                return "ID 必须是数字。"
            return "已移除置顶。" if mem.unpin(sid, pid) else f"未找到置顶 #{pid}。"
        entry = mem.pin(sid, text)
        return f"已置顶 L1 #{entry['id']}：{entry['content']}"

    def cmd_remember(args: str, ctx: dict):
        text = args.strip()
        if not text:
            return f"用法：/remember [分类:{'/'.join(LONG_CATEGORIES)}] <标题>: <内容>"
        parts = text.split(None, 1)
        if len(parts) == 2 and parts[0] in LONG_CATEGORIES:
            category, rest = parts[0], parts[1]
        else:
            category, rest = "project", text
        if ":" in rest:
            title, body = rest.split(":", 1)
        elif "：" in rest:
            title, body = rest.split("：", 1)
        else:
            title, body = rest[:50], rest
        entry = mem.save_long(category, title.strip(), body.strip())
        return f"已写入 L3 长期记忆 [{entry['id']}] ({entry['category']}) -> {mem.root / entry['file']}"

    api.register_command("memory", "查看 L1/L2/L3 三层记忆", cmd_memory)
    api.register_command("pin", "添加或删除 L1 会话置顶要求", cmd_pin)
    api.register_command("remember", "直接写入 L3 长期 Markdown 记忆", cmd_remember)
    return mem

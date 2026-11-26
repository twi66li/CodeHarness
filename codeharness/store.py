"""Append-only events are the source of messages, usage and tool evidence."""

from datetime import datetime, timezone
from hashlib import sha256
import json
from pathlib import Path
import sqlite3
import uuid


def now() -> str:
    return datetime.now(timezone.utc).isoformat()


class Store:
    def __init__(self, path: Path):
        path.parent.mkdir(parents=True, exist_ok=True)
        self.path = path
        self.db = sqlite3.connect(path)
        self.db.row_factory = sqlite3.Row
        self._blob_keys = {}
        self._heads = {}
        self.db.executescript("""
            PRAGMA journal_mode=WAL;
            CREATE TABLE IF NOT EXISTS sessions (
                id TEXT PRIMARY KEY, root_id TEXT NOT NULL, parent_id TEXT,
                workspace TEXT NOT NULL, model TEXT NOT NULL, status TEXT NOT NULL,
                created_at TEXT NOT NULL, updated_at TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS events (
                id INTEGER PRIMARY KEY AUTOINCREMENT, session_id TEXT NOT NULL,
                time TEXT NOT NULL, kind TEXT NOT NULL, data TEXT NOT NULL
            );
            CREATE INDEX IF NOT EXISTS events_session ON events(session_id, id);
            CREATE INDEX IF NOT EXISTS events_session_kind ON events(session_id, kind, id);
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, root_id TEXT NOT NULL, content TEXT NOT NULL
            );
            CREATE TABLE IF NOT EXISTS blobs (hash TEXT PRIMARY KEY, content TEXT NOT NULL);
            CREATE TABLE IF NOT EXISTS usage_totals (
                root_id TEXT PRIMARY KEY, requests INTEGER NOT NULL, input_tokens INTEGER NOT NULL,
                output_tokens INTEGER NOT NULL, cached_tokens INTEGER NOT NULL, estimated INTEGER NOT NULL
            );
        """)
        self._backfill_usage()

    def close(self):
        self.db.close()

    def create(self, workspace: Path, model: str, parent_id: str | None = None) -> str:
        sid = uuid.uuid4().hex[:12]
        root = self.session(parent_id)["root_id"] if parent_id else sid
        stamp = now()
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                            (sid, root, parent_id, str(workspace.resolve()), model, "running", stamp, stamp))
            self.db.execute("INSERT OR IGNORE INTO usage_totals VALUES (?,0,0,0,0,0)", (root,))
        return sid

    def session(self, sid: str) -> dict:
        row = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise ValueError(f"会话不存在：{sid}")
        return dict(row)

    def sessions(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM sessions ORDER BY created_at DESC")]

    def append(self, sid: str, kind: str, data: dict):
        stored = data
        blobs = {}
        if kind == "model_request":
            stored = dict(data)
            if "messages" in stored:
                stored["message_refs"] = [self._blob_ref(message, blobs) for message in stored.pop("messages")]
            if "tools" in stored:
                stored["tools_ref"] = self._blob_ref(stored.pop("tools"), blobs)
        checkpoint = kind == "checkpoint" and "files" in data
        with self.db:
            if checkpoint:
                self.db.execute("BEGIN IMMEDIATE")
                stored, depth = self._encode_checkpoint(sid, data["files"])
            if blobs:
                self.db.executemany("INSERT OR IGNORE INTO blobs VALUES (?,?)",
                                    ((key, content) for content, key in blobs.items()))
            cursor = self.db.execute("INSERT INTO events(session_id,time,kind,data) VALUES (?,?,?,?)",
                                     (sid, now(), kind, json.dumps(stored, ensure_ascii=False)))
            if kind in {"model_request", "usage"}:
                self.db.execute("""UPDATE usage_totals SET requests=requests+?, input_tokens=input_tokens+?,
                    output_tokens=output_tokens+?, cached_tokens=cached_tokens+?, estimated=estimated OR ?
                    WHERE root_id=(SELECT root_id FROM sessions WHERE id=?)""", (*self._usage_delta(kind, data), sid))
        self._blob_keys.update(blobs)
        if checkpoint:
            self._heads[sid] = (cursor.lastrowid, depth, dict(data["files"]))

    def _blob_ref(self, value, pending: dict) -> str:
        content = json.dumps(value, ensure_ascii=False)
        key = self._blob_keys.get(content) or pending.get(content)
        if key is None:
            key = sha256(content.encode("utf-8")).hexdigest()
            pending[content] = key
        return key

    def _latest_checkpoint(self, sid: str):
        return self.db.execute("SELECT id,data FROM events WHERE session_id=? AND kind='checkpoint' ORDER BY id DESC LIMIT 1",
                               (sid,)).fetchone()

    @staticmethod
    def _apply_checkpoint(files: dict, delta: dict) -> dict:
        merged = {**files, **delta["changed"]}
        for path in delta["removed"]:
            merged.pop(path, None)
        return merged

    def _decode_checkpoint(self, sid: str, event_id: int, data: dict) -> tuple[dict, int]:
        layers = []
        while "base" in data:
            layers.append(data)
            base = data["base"]
            row = self.db.execute("SELECT data FROM events WHERE session_id=? AND kind='checkpoint' AND id=?",
                                  (sid, base)).fetchone()
            if row is None or base >= event_id:
                raise ValueError("检查点缺少有效的基准")
            event_id, data = base, json.loads(row["data"])
        files = data["files"]
        for delta in reversed(layers):
            files = self._apply_checkpoint(files, delta)
        return files, len(layers)

    def _encode_checkpoint(self, sid: str, files: dict) -> tuple[dict, int]:
        row = self._latest_checkpoint(sid)
        if row is None:
            return {"files": files}, 0
        cached = self._heads.get(sid)
        if cached and cached[0] == row["id"]:
            _, depth, previous = cached
        else:
            previous, depth = self._decode_checkpoint(sid, row["id"], json.loads(row["data"]))
        if depth == 19:
            return {"files": files}, 0
        return {"base": row["id"], "changed": {name: value for name, value in files.items() if previous.get(name) != value},
                "removed": sorted(previous.keys() - files.keys())}, depth + 1

    def files_at(self, sid: str) -> dict | None:
        row = self._latest_checkpoint(sid)
        if row is None:
            return None
        cached = self._heads.get(sid)
        if cached and cached[0] == row["id"]:
            return dict(cached[2])
        files, depth = self._decode_checkpoint(sid, row["id"], json.loads(row["data"]))
        self._heads[sid] = (row["id"], depth, files)
        return dict(files)

    def status(self, sid: str, status: str):
        with self.db:
            self.db.execute("UPDATE sessions SET status=?,updated_at=? WHERE id=?", (status, now(), sid))
            self.db.execute("INSERT INTO events(session_id,time,kind,data) VALUES (?,?,?,?)",
                            (sid, now(), "status", json.dumps({"status": status})))

    def events(self, sid: str, *, after: int = 0, expand: bool = True) -> list[dict]:
        events = [{"id": r["id"], "time": r["time"], "kind": r["kind"], "data": json.loads(r["data"])}
                  for r in self.db.execute("SELECT * FROM events WHERE session_id=? AND id>? ORDER BY id", (sid, after))]
        if not expand:
            return events
        cached_blobs = {}
        latest = None
        files = {}

        def read_blob(key):
            if key not in cached_blobs:
                row = self.db.execute("SELECT content FROM blobs WHERE hash=?", (key,)).fetchone()
                if row is None:
                    raise ValueError("模型记录引用的内容不存在")
                cached_blobs[key] = row["content"]
            return json.loads(cached_blobs[key])

        for event in events:
            data = event["data"]
            if event["kind"] == "model_request":
                if "message_refs" in data:
                    data["messages"] = [read_blob(ref) for ref in data.pop("message_refs")]
                if "tools_ref" in data:
                    data["tools"] = read_blob(data.pop("tools_ref"))
            elif event["kind"] == "checkpoint":
                if "files" in data:
                    files = data["files"]
                elif data["base"] == latest:
                    files = self._apply_checkpoint(files, data)
                else:
                    files, _ = self._decode_checkpoint(sid, event["id"], data)
                event["data"] = {"files": files}
                latest = event["id"]
        return events

    def messages(self, sid: str) -> list[dict]:
        messages = []
        for row in self.db.execute("SELECT kind,data FROM events WHERE session_id=? AND kind IN ('message','skill_injected') ORDER BY id", (sid,)):
            data = json.loads(row["data"])
            messages.append(data if row["kind"] == "message" else data["message"])
        return messages

    def artifact(self, sid: str, content: str) -> str:
        aid = uuid.uuid4().hex[:12]
        with self.db:
            self.db.execute("INSERT INTO artifacts VALUES (?,?,?)",
                            (aid, self.session(sid)["root_id"], content))
        return aid

    def read_artifact(self, sid: str, aid: str) -> str:
        row = self.db.execute("SELECT content FROM artifacts WHERE id=? AND root_id=?",
                              (aid, self.session(sid)["root_id"])).fetchone()
        if row is None:
            raise ValueError("产物不存在或不属于本次任务")
        return row["content"]

    @staticmethod
    def _usage_delta(kind: str, data: dict) -> tuple:
        if kind == "model_request":
            return 1, 0, 0, 0, 0
        return 0, data.get("input_tokens", 0), data.get("output_tokens", 0), data.get("cached_tokens", 0), bool(data.get("estimated"))

    def _backfill_usage(self):
        query = "SELECT root_id FROM sessions EXCEPT SELECT root_id FROM usage_totals"
        if self.db.execute(query).fetchone() is None:
            return
        with self.db:
            self.db.execute("BEGIN IMMEDIATE")
            for root, in self.db.execute(query).fetchall():
                totals = [0, 0, 0, 0, 0]
                for row in self.db.execute("""SELECT e.kind,e.data FROM events e JOIN sessions s ON s.id=e.session_id
                        WHERE s.root_id=? AND e.kind IN ('model_request','usage')""", (root,)):
                    delta = self._usage_delta(row["kind"], json.loads(row["data"]) if row["kind"] == "usage" else {})
                    for index in range(4):
                        totals[index] += delta[index]
                    totals[4] |= delta[4]
                self.db.execute("INSERT INTO usage_totals VALUES (?,?,?,?,?,?)", (root, *totals))

    def usage(self, sid: str) -> dict:
        row = self.db.execute("""SELECT u.requests,u.input_tokens,u.output_tokens,u.cached_tokens,u.estimated
            FROM usage_totals u JOIN sessions s ON s.root_id=u.root_id WHERE s.id=?""", (sid,)).fetchone()
        if row is None:
            raise ValueError(f"会话不存在：{sid}")
        return {**dict(row), "estimated": bool(row["estimated"])}

    def repair_pending(self, sid: str):
        """Never replay an uncertain side effect after an interrupted process."""
        events = self.events(sid, expand=False)
        answered = {e["data"]["tool_call_id"] for e in events
                    if e["kind"] == "message" and e["data"]["role"] == "tool"}
        started = {e["data"]["call_id"]: e["data"].get("effect") for e in events if e["kind"] == "tool_started"}
        finished = {e["data"]["call_id"]: e["data"]["result"] for e in events if e["kind"] == "tool_finished"}
        for event in events:
            if event["kind"] != "message":
                continue
            for call in event["data"].get("tool_calls", []):
                cid = call["id"]
                if cid in answered:
                    continue
                if cid in finished:
                    result = finished[cid]
                elif started.get(cid) == "read":
                    result = {"ok": False, "error": "只读工具调用被中断，可以安全地重新执行。"}
                elif cid in started:
                    result = {"ok": False, "error":
                        "执行被中断，工具是否产生副作用尚不确定。先检查文件或测试状态，不要直接重复写操作。"}
                else:
                    result = {"ok": False, "error": "前序调用中断，本工具调用尚未执行。"}
                self.append(sid, "message", {"role": "tool", "tool_call_id": cid,
                                           "content": json.dumps(result, ensure_ascii=False)})
                self.append(sid, "tool_reconciled", {"call_id": cid, "completed": cid in finished,
                                                     "started": cid in started})
                answered.add(cid)

    # ---------- Session Tree (Fork & Inspect) ----------

    def turns(self, sid: str) -> list[dict]:
        """List branchable turn checkpoints (completed assistant replies) in a session."""
        self.session(sid)
        events = self.events(sid, expand=False)
        turns: list[dict] = []
        last_user = ""
        for event in events:
            if event["kind"] != "message":
                continue
            msg = event["data"]
            role = msg.get("role")
            if role == "user":
                content = str(msg.get("content", ""))
                if not content.startswith("[") and not content.startswith("恢复检查："):
                    last_user = content.partition("\n")[0][:80]
            elif role == "assistant" and not msg.get("tool_calls"):
                turns.append({
                    "turn": len(turns) + 1,
                    "event_id": event["id"],
                    "user": last_user,
                    "assistant": str(msg.get("content", "")).splitlines()[0][:80] if msg.get("content") else "",
                    "time": event["time"],
                })
        return turns

    def fork(self, sid: str, up_to_event_id: int | None = None, *, label: str = "") -> str:
        """Fork a new writable branch session up to a specific event id (or latest)."""
        source = self.session(sid)
        if source["parent_id"] is not None:
            raise ValueError("不能从只读子任务分叉，请从主会话分叉")
        events = self.events(sid, expand=True)
        if not events:
            raise ValueError("原会话没有可分叉的事件")
        cutoff = up_to_event_id if up_to_event_id is not None else events[-1]["id"]
        selected = [e for e in events if e["id"] <= cutoff]
        if not selected:
            raise ValueError(f"事件 ID {cutoff} 不在会话 {sid} 中")
        if up_to_event_id is not None and not any(e["id"] == cutoff for e in selected):
            raise ValueError(f"会话 {sid} 中不存在事件 ID {cutoff}")

        if not any(event["kind"] == "baseline" for event in selected):
            raise ValueError("分叉位置早于工作区基线")

        new_sid = self.create(Path(source["workspace"]), source["model"], parent_id=None)
        artifact_map: dict[str, str] = {}

        def remap_artifact(data):
            old_id = data.get("artifact_id")
            if not isinstance(old_id, str):
                return False
            if old_id not in artifact_map:
                try:
                    content = self.read_artifact(sid, old_id)
                except ValueError:
                    return False
                artifact_map[old_id] = self.artifact(new_sid, content)
            data["artifact_id"] = artifact_map[old_id]
            return True

        def remap_json_field(data, field):
            try:
                payload = json.loads(data[field])
            except (KeyError, ValueError, TypeError):
                return
            if isinstance(payload, dict) and remap_artifact(payload):
                data[field] = json.dumps(payload, ensure_ascii=False)

        def remap_message(message):
            if message.get("role") == "tool":
                remap_json_field(message, "content")
            for call in message.get("tool_calls", ()):
                if call["function"]["name"] == "read_artifact":
                    remap_json_field(call["function"], "arguments")

        self.append(new_sid, "branch_origin", {
            "from_session": sid,
            "from_event_id": selected[-1]["id"],
            "label": label.strip(),
        })
        copy_kinds = {"baseline", "message", "skill_loaded", "skill_injected",
                      "compact_checkpoint", "checkpoint", "verification", "tool_started", "tool_finished"}
        for event in selected:
            kind, data = event["kind"], event["data"]
            if kind == "message":
                remap_message(data)
            elif kind == "compact_checkpoint":
                for message in data["messages"]:
                    remap_message(message)
            elif kind == "tool_finished":
                remap_artifact(data["result"])
            elif kind == "verification":
                remap_artifact(data)
            if kind in copy_kinds:
                self.append(new_sid, kind, data)
        self.repair_pending(new_sid)
        self.status(new_sid, "completed")
        return new_sid

    def branch_origin(self, sid: str) -> dict | None:
        row = self.db.execute(
            "SELECT data FROM events WHERE session_id=? AND kind='branch_origin' ORDER BY id ASC LIMIT 1",
            (sid,)).fetchone()
        return json.loads(row["data"]) if row else None

    def session_tree(self, sid: str) -> dict:
        """Build the branch lineage tree containing the given session."""
        self.session(sid)
        all_sessions = {row["id"]: row for row in self.sessions() if row["parent_id"] is None}
        origins: dict[str, dict] = {}
        for row in self.db.execute("SELECT session_id, data FROM events WHERE kind='branch_origin' ORDER BY id"):
            origins.setdefault(row["session_id"], json.loads(row["data"]))

        # Climb to the ancestor root of this branch family.
        root = sid
        seen = {root}
        while root in origins and origins[root]["from_session"] in all_sessions:
            parent = origins[root]["from_session"]
            if parent in seen:
                break
            seen.add(parent)
            root = parent

        children: dict[str, list[str]] = {}
        for child_id, origin in origins.items():
            if child_id in all_sessions:
                children.setdefault(origin["from_session"], []).append(child_id)

        nodes: list[dict] = []

        def walk(curr: str, depth: int):
            meta = all_sessions.get(curr)
            if not meta:
                return
            origin = origins.get(curr)
            nodes.append({
                "id": curr,
                "depth": depth,
                "current": curr == sid,
                "model": meta["model"],
                "status": meta["status"],
                "from_event_id": origin["from_event_id"] if origin else None,
                "label": origin.get("label", "") if origin else "",
            })
            for child in children.get(curr, ()):
                walk(child, depth + 1)

        walk(root, 0)
        return {"root": root, "current": sid, "branches": nodes, "turns": self.turns(sid)}

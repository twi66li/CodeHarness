"""Append-only events are the source of messages, usage and tool evidence."""

from datetime import datetime, timezone
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
            CREATE TABLE IF NOT EXISTS artifacts (
                id TEXT PRIMARY KEY, root_id TEXT NOT NULL, content TEXT NOT NULL
            );
        """)

    def close(self):
        self.db.close()

    def create(self, workspace: Path, model: str, parent_id: str | None = None) -> str:
        sid = uuid.uuid4().hex[:12]
        root = self.session(parent_id)["root_id"] if parent_id else sid
        stamp = now()
        with self.db:
            self.db.execute("INSERT INTO sessions VALUES (?,?,?,?,?,?,?,?)",
                            (sid, root, parent_id, str(workspace.resolve()), model, "running", stamp, stamp))
        return sid

    def session(self, sid: str) -> dict:
        row = self.db.execute("SELECT * FROM sessions WHERE id=?", (sid,)).fetchone()
        if row is None:
            raise ValueError(f"会话不存在：{sid}")
        return dict(row)

    def sessions(self) -> list[dict]:
        return [dict(r) for r in self.db.execute("SELECT * FROM sessions ORDER BY created_at DESC")]

    def append(self, sid: str, kind: str, data: dict):
        with self.db:
            self.db.execute("INSERT INTO events(session_id,time,kind,data) VALUES (?,?,?,?)",
                            (sid, now(), kind, json.dumps(data, ensure_ascii=False)))

    def status(self, sid: str, status: str):
        with self.db:
            self.db.execute("UPDATE sessions SET status=?,updated_at=? WHERE id=?", (status, now(), sid))
            self.db.execute("INSERT INTO events(session_id,time,kind,data) VALUES (?,?,?,?)",
                            (sid, now(), "status", json.dumps({"status": status})))

    def events(self, sid: str) -> list[dict]:
        return [{"id": r["id"], "time": r["time"], "kind": r["kind"], "data": json.loads(r["data"])}
                for r in self.db.execute("SELECT * FROM events WHERE session_id=? ORDER BY id", (sid,))]

    def messages(self, sid: str) -> list[dict]:
        return [e["data"] for e in self.events(sid) if e["kind"] == "message"]

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

    def usage(self, sid: str) -> dict:
        rows = self.db.execute("""SELECT e.kind,e.data FROM events e JOIN sessions s ON s.id=e.session_id
            WHERE s.root_id=? AND e.kind IN ('model_request','usage')""", (self.session(sid)["root_id"],))
        result = {"requests": 0, "input_tokens": 0, "output_tokens": 0, "estimated": False}
        for row in rows:
            if row["kind"] == "model_request":
                result["requests"] += 1
            else:
                data = json.loads(row["data"])
                result["input_tokens"] += data["input_tokens"]
                result["output_tokens"] += data["output_tokens"]
                result["estimated"] |= data.get("estimated", False)
        return result

    def repair_pending(self, sid: str):
        """Never replay an uncertain side effect after an interrupted process."""
        events = self.events(sid)
        answered = {e["data"]["tool_call_id"] for e in events
                    if e["kind"] == "message" and e["data"]["role"] == "tool"}
        finished = {e["data"]["call_id"]: e["data"]["result"] for e in events if e["kind"] == "tool_finished"}
        for event in events:
            if event["kind"] != "message":
                continue
            for call in event["data"].get("tool_calls", []):
                cid = call["id"]
                if cid in answered:
                    continue
                result = finished.get(cid, {"ok": False, "error":
                    "执行被中断，工具是否产生副作用尚不确定。先检查文件或测试状态，不要直接重复写操作。"})
                self.append(sid, "message", {"role": "tool", "tool_call_id": cid,
                                           "content": json.dumps(result, ensure_ascii=False)})
                self.append(sid, "tool_reconciled", {"call_id": cid, "completed": cid in finished})
                answered.add(cid)

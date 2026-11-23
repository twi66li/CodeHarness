"""从本地基准评测会话恢复失败补丁当时的夹具文件。"""

import argparse
from contextlib import closing
import json
import os
from pathlib import Path
import re
import sqlite3
from tempfile import TemporaryDirectory

from codeharness.benchmark import materialize
from codeharness.benchmark_large import large_tasks
from codeharness.benchmark_tasks import ALL_TASKS
from codeharness.cli import load_env
from codeharness.tools import Policy, Registry, ToolError, Workspace, register_workspace_tools


WRITES = {"write_file", "edit_file", "apply_patch"}
LOCAL_PATH = re.compile(r"(?i)(?:\b[a-z]:[\\/]|\\\\[^\\\s]+\\|/(?:home|Users|mnt|tmp)/)")
SECRET = re.compile(r"(?i)(?:\bsk-[a-z0-9_-]{16,}|\bBearer\s+[a-z0-9._-]{12,}|-----BEGIN [A-Z ]*PRIVATE KEY-----)")


def cases(benchmarks):
    seen = set()
    for directory in sorted(benchmarks.iterdir()):
        report = directory / "report.json"
        if not directory.name.startswith(("s13-", "magpie-")) or not report.is_file():
            continue
        for row in json.loads(report.read_text(encoding="utf-8"))["cases"]:
            if not row.get("workspace") or not row.get("session_id"):
                continue
            database = (directory / row["workspace"].replace("\\", "/")).parent / "state.sqlite3"
            key = database.resolve(), row["session_id"]
            if database.is_file() and key not in seen:
                seen.add(key)
                yield row["task"], database, row["session_id"]


def private_checker():
    settings = dict(os.environ)
    values = set()
    for path in (Path(".env"), Path(".env.magpie"), Path(".env.bailian")):
        if path.is_file():
            values.update(value for key, value in load_env(path).items()
                          if re.search(r"KEY|PASSWORD|SECRET|TOKEN", key, re.I) and len(value) >= 8)
    values.update(value for key, value in settings.items()
                  if re.search(r"API_KEY|PASSWORD|SECRET|ACCESS_TOKEN", key, re.I) and len(value) >= 8)
    username = os.environ.get("USERNAME") or os.environ.get("USER") or ""
    user = re.compile(r"\b" + re.escape(username) + r"\b", re.I) if len(username) >= 3 else None
    return lambda text: (LOCAL_PATH.search(text) or SECRET.search(text)
                         or (user and user.search(text)) or any(value in text for value in values))


def patch_files(patch, workspace):
    paths = set()
    for line in patch.splitlines():
        marker = next((value for value in ("--- ", "+++ ", "*** Update File: ", "*** Delete File: ", "*** Add File: ")
                       if line.startswith(value)), None)
        if marker is None:
            continue
        name = line[len(marker):].split("\t", 1)[0]
        if name == "/dev/null":
            continue
        prefix = "a/" if line.startswith("--- ") else "b/"
        if marker in {"--- ", "+++ "} and name.startswith(prefix):
            name = name[2:]
        # A misplaced hunk line may look like a header. Only keep existing task files.
        try:
            target = workspace.path(name)
        except ToolError:
            continue
        if target.is_file():
            paths.add(target.relative_to(workspace.root).as_posix())
    return {name: workspace.path(name).read_bytes() for name in sorted(paths)}


def failures(database, session, task):
    with closing(sqlite3.connect(database.resolve().as_uri() + "?mode=ro", uri=True)) as db:
        events = db.execute("SELECT kind, data FROM events WHERE session_id=? ORDER BY id", (session,)).fetchall()
    with TemporaryDirectory() as temp:
        workspace = Workspace(Path(temp))
        materialize(workspace.root, task.files)
        registry = Registry(workspace, Policy(allow_write=True))
        register_workspace_tools(registry)
        calls = {}
        can_replay = True
        for kind, raw in events:
            data = json.loads(raw)
            if kind == "message" and data.get("role") == "assistant":
                for call in data.get("tool_calls", ()):
                    calls[call["id"]] = call["function"]["arguments"]
            if kind != "tool_finished" or data["name"] not in WRITES:
                continue
            name, result = data["name"], data["result"]
            try:
                args = json.loads(calls.get(data["call_id"], "null"))
            except (TypeError, ValueError):
                args = None
            if not result["ok"]:
                if name == "apply_patch":
                    patch = args.get("patch") if isinstance(args, dict) else None
                    files = patch_files(patch, workspace) if can_replay and isinstance(patch, str) else None
                    reason = None if files else "无法恢复前置写入或定位目标文件"
                    yield patch, result.get("error", ""), files, reason
                continue
            if can_replay:
                try:
                    actual = registry.invoke(name, args)
                    saved = result.get("output")
                    can_replay = saved is None or actual == saved
                except (ToolError, OSError, UnicodeError):
                    can_replay = False


def export(benchmarks, output):
    tasks = {task.id: task for task in (*ALL_TASKS, *large_tasks())}
    private = private_checker()
    output.mkdir(parents=True, exist_ok=False)
    count = restored = 0
    for task_id, database, session in cases(benchmarks):
        for patch, error, files, reason in failures(database, session, tasks[task_id]):
            count += 1
            folder = output / f"{count:03}"
            folder.mkdir()
            if private(patch or "") or any(private(name) or private(raw.decode("utf-8")) for name, raw in (files or {}).items()):
                reason = "内容含本机标识或凭据形态，未导出"
                patch, files = None, None
            if patch is not None:
                (folder / "patch.diff").write_bytes(patch.encode("utf-8"))
            if not reason:
                restored += 1
                for name, raw in files.items():
                    path = folder / "files" / name
                    path.parent.mkdir(parents=True, exist_ok=True)
                    path.write_bytes(raw)
            meta = {"case": task_id, "session_path": database.relative_to(benchmarks).as_posix(),
                    "error": "已省略本机信息" if private(error) else error, "skip_reason": reason}
            (folder / "meta.json").write_text(json.dumps(meta, ensure_ascii=False, indent=2) + "\n",
                                              encoding="utf-8", newline="\n")
    return {"failures": count, "restored": restored}


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--benchmarks", type=Path, default=Path(".codeharness/benchmarks"))
    parser.add_argument("--output", type=Path, default=Path("tests/fixtures/real_patches"))
    args = parser.parse_args()
    print(json.dumps(export(args.benchmarks, args.output)))


if __name__ == "__main__":
    main()

"""Tools share path checks and a policy gate. Hooks cannot bypass that gate."""

from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
from typing import Callable


class ToolError(RuntimeError):
    pass


HIDDEN = {".git", ".venv", "venv", ".idea", ".codeharness", ".ssh", ".aws", "node_modules", "__pycache__"}


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError(f"工作区不存在：{self.root}")

    def path(self, name: str) -> Path:
        target = (self.root / name).resolve()
        if not target.is_relative_to(self.root):
            raise ToolError("路径超出工作区")
        parts = target.relative_to(self.root).parts
        if any(p in HIDDEN or p.startswith(".env") for p in parts):
            raise ToolError("该路径属于受保护的配置或运行目录")
        return target

    def files(self, name: str = "."):
        start = self.path(name)
        if start.is_file():
            yield start
            return
        for current, dirs, names in os.walk(start):
            dirs[:] = sorted(d for d in dirs if d not in HIDDEN and not d.startswith(".env")
                             and not (Path(current) / d).is_symlink())
            for filename in sorted(names):
                file = Path(current) / filename
                if not filename.startswith(".env") and not file.is_symlink():
                    yield self.path(str(file.relative_to(self.root)))

    def snapshot(self) -> dict:
        return {str(p.relative_to(self.root)).replace("\\", "/"): digest(p.read_bytes())
                for p in self.files() if p.stat().st_size <= 2_000_000}


def digest(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    execute: Callable
    effect: str = "read"

    def schema(self) -> dict:
        return {"type": "function", "function": {"name": self.name,
                "description": self.description, "parameters": self.parameters}}


def parameters(properties: dict, required: list[str] | None = None) -> dict:
    return {"type": "object", "properties": properties, "required": required or [], "additionalProperties": False}


def string(description: str) -> dict:
    return {"type": "string", "description": description}


def integer(description: str) -> dict:
    return {"type": "integer", "description": description}


class Policy:
    def __init__(self, allow_write=False, allow_exec=False, readonly=False, confirm: Callable | None = None):
        self.allow_write = allow_write
        self.allow_exec = allow_exec
        self.readonly = readonly
        self.confirm = confirm

    def authorize(self, tool: Tool, args: dict):
        if tool.effect in {"read", "delegate"}:
            return
        if self.readonly:
            raise ToolError("只读子任务不允许修改文件或执行代码")
        allowed = self.allow_write if tool.effect == "write" else self.allow_exec
        if not allowed and not (self.confirm and self.confirm(tool.name, args)):
            raise ToolError(f"权限被拒绝：{tool.name}。需要用户授权，不要绕过。")


class Registry:
    def __init__(self, workspace: Workspace, policy: Policy):
        self.workspace = workspace
        self.policy = policy
        self.tools: dict[str, Tool] = {}
        self.before: list[Callable] = []
        self.after: list[Callable] = []

    def register(self, tool: Tool):
        if tool.name in self.tools:
            raise ValueError(f"工具已注册：{tool.name}")
        if tool.effect not in {"read", "write", "execute", "delegate"}:
            raise ValueError("工具必须声明 read/write/execute/delegate 权限类别")
        self.tools[tool.name] = tool

    def schemas(self) -> list[dict]:
        return [tool.schema() for tool in self.tools.values()]

    def invoke(self, name: str, args: dict) -> dict:
        if name not in self.tools:
            raise ToolError(f"未知工具：{name}")
        tool = self.tools[name]
        if not isinstance(args, dict):
            raise ToolError("工具参数必须是 JSON 对象")
        props = tool.parameters["properties"]
        if set(args) - set(props) or set(tool.parameters.get("required", [])) - set(args):
            raise ToolError("工具参数缺失或含未知字段")
        for key, value in args.items():
            kind = props[key]["type"]
            valid = isinstance(value, str) if kind == "string" else type(value) is int
            if not valid or ("enum" in props[key] and value not in props[key]["enum"]):
                raise ToolError(f"工具参数类型或取值错误：{key}")
        for hook in self.before:
            reason = hook(name, args)
            if reason:
                raise ToolError(str(reason))
        # Recheck after hooks so an argument change never skips policy enforcement.
        self.policy.authorize(tool, args)
        result = tool.execute(**args)
        for hook in self.after:
            hook(name, args, result)
        return result


def register_workspace_tools(registry: Registry):
    workspace = registry.workspace

    def list_files(path="."):
        names = []
        for file in workspace.files(path):
            names.append(str(file.relative_to(workspace.root)).replace("\\", "/"))
            if len(names) >= 200:
                return {"files": names, "truncated": True}
        return {"files": names, "truncated": False}

    def read_file(path, start_line=1, lines=160):
        if start_line < 1 or not 1 <= lines <= 300:
            raise ToolError("start_line 必须大于 0，lines 应在 1 到 300 之间")
        target = workspace.path(path)
        if target.stat().st_size > 2_000_000:
            raise ToolError("文件超过 2MB，请缩小工作区或读取文本产物")
        raw = target.read_bytes()
        text = raw.decode("utf-8-sig")
        content = text.splitlines()
        return {"path": path, "sha256": digest(raw), "total_lines": len(content),
                "content": "\n".join(f"{i + 1}: {line}" for i, line in
                    enumerate(content[start_line - 1:start_line - 1 + lines], start_line - 1))}

    def search(query, path="."):
        if not query:
            raise ToolError("搜索内容不能为空")
        matches = []
        for file in workspace.files(path):
            if file.stat().st_size > 2_000_000:
                continue
            try:
                text = file.read_text(encoding="utf-8-sig")
            except UnicodeError:
                continue
            for number, line in enumerate(text.splitlines(), 1):
                if query.casefold() in line.casefold():
                    matches.append({"path": str(file.relative_to(workspace.root)).replace("\\", "/"),
                                    "line": number, "text": line[:400]})
                    if len(matches) >= 40:
                        return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def edit_file(path, old_text, new_text, expected_sha256):
        target = workspace.path(path)
        raw = target.read_bytes()
        if digest(raw) != expected_sha256:
            raise ToolError("文件已变化，请重新读取最新内容后再编辑")
        text = raw.decode("utf-8")
        if not old_text or text.count(old_text) != 1:
            raise ToolError("old_text 必须精确匹配且只出现一次；请读取更明确的上下文")
        updated = text.replace(old_text, new_text, 1).encode("utf-8")
        target.write_bytes(updated)
        return {"path": path, "before_sha256": digest(raw), "after_sha256": digest(updated)}

    def write_file(path, content):
        target = workspace.path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids overwriting a file created after the model read.
        with target.open("x", encoding="utf-8", newline="") as file:
            file.write(content)
        return {"path": path, "sha256": digest(target.read_bytes())}

    def run_tests(path="tests", runner="unittest"):
        target = workspace.path(path)
        if runner == "unittest":
            if not target.is_dir():
                raise ToolError("unittest 的 path 必须是测试目录")
            command = [sys.executable, "-m", "unittest", "discover", "-s", str(target), "-v"]
        else:
            command = [sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"]
        environment = dict(os.environ)
        for key in list(environment):
            if key.upper() in {"OPENAI_API_KEY", "CODEHARNESS_API_KEY"}:
                environment.pop(key)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        process = subprocess.Popen(command, cwd=workspace.root, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output, _ = process.communicate(timeout=60)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            process.kill()
            process.communicate()
            raise
        text = output.decode("utf-8", errors="replace")
        collected = re.search(r"Ran (\d+) tests?", text) if runner == "unittest" else None
        no_tests = runner == "unittest" and (collected is None or int(collected.group(1)) == 0)
        # Missing pytest is an environment failure, not evidence of a code defect.
        return {"command": command[1:], "exit_code": process.returncode,
                "passed": process.returncode == 0 and not no_tests, "output": text,
                "failure_lines": [line for line in text.splitlines() if any(
                    term in line for term in ("FAIL", "ERROR", "AssertionError", "File \""))][:40]}

    for tool in [
        Tool("list_files", "列出工作区文件，排除凭据、Git 和运行目录。", parameters({"path": string("相对目录")}), list_files),
        Tool("read_file", "读取带行号的文本及用于编辑的 sha256。", parameters({
            "path": string("相对文件路径"), "start_line": integer("起始行，默认 1"),
            "lines": integer("行数，默认 160，上限 300")}, ["path"]), read_file),
        Tool("search", "按字面内容搜索代码，返回路径、行号和匹配片段。", parameters({
            "query": string("搜索文本"), "path": string("相对目录或文件")}, ["query"]), search),
        Tool("edit_file", "精确替换一次文本，sha256 必须来自最新读取。", parameters({
            "path": string("相对文件路径"), "old_text": string("唯一匹配的原文本"),
            "new_text": string("替换文本"), "expected_sha256": string("最新文件摘要")},
            ["path", "old_text", "new_text", "expected_sha256"]), edit_file, "write"),
        Tool("write_file", "创建新文件，已有文件应使用 edit_file。", parameters({
            "path": string("相对文件路径"), "content": string("文件内容")}, ["path", "content"]), write_file, "write"),
        Tool("run_tests", "在工作区运行测试，最多 60 秒；会执行项目代码，需要执行授权。", parameters({
            "path": string("测试目录或 pytest 文件，默认 tests"),
            "runner": {"type": "string", "enum": ["unittest", "pytest"]}}), run_tests, "execute"),
    ]:
        registry.register(tool)

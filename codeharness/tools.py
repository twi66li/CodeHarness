"""Tools share path checks and a policy gate. Hooks cannot bypass that gate."""

from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import time
from typing import Callable


class ToolError(RuntimeError):
    pass


HIDDEN = {".git", ".venv", "venv", ".idea", ".codeharness", ".ssh", ".aws", "node_modules", "__pycache__"}


def protected(name: str) -> bool:
    name = name.casefold()
    return name in HIDDEN or name.startswith(".env")


class Workspace:
    def __init__(self, root: Path):
        self.root = root.resolve()
        if not self.root.is_dir():
            raise ValueError(f"工作区不存在：{self.root}")
        self._digest_cache: dict[str, tuple[int, int, str]] = {}

    def path(self, name: str) -> Path:
        candidate = self.root / name
        if candidate.is_relative_to(self.root) and any(protected(p) for p in candidate.relative_to(self.root).parts):
            raise ToolError("该路径属于受保护的配置或运行目录")
        target = candidate.resolve()
        if not target.is_relative_to(self.root):
            raise ToolError("路径超出工作区")
        parts = target.relative_to(self.root).parts
        if any(protected(p) for p in parts):
            raise ToolError("该路径属于受保护的配置或运行目录")
        return target

    def files(self, name: str = "."):
        start = self.path(name)
        if start.is_file():
            yield start
            return
        for current, dirs, names in os.walk(start):
            dirs[:] = sorted(d for d in dirs if not protected(d)
                             and not (Path(current) / d).is_symlink())
            for filename in sorted(names):
                file = Path(current) / filename
                if not protected(filename) and not file.is_symlink():
                    yield self.path(str(file.relative_to(self.root)))

    def _cache_digest(self, target: Path, raw: bytes | None = None) -> str:
        rel = str(target.relative_to(self.root)).replace("\\", "/")
        st = target.stat()
        sha = digest(target.read_bytes() if raw is None else raw)
        self._digest_cache[rel] = (st.st_mtime_ns, st.st_size, sha)
        return sha

    def snapshot(self, use_cache: bool = True) -> dict:
        result = {}
        for p in self.files():
            st = p.stat()
            if st.st_size > 2_000_000:
                continue
            rel = str(p.relative_to(self.root)).replace("\\", "/")
            cached = self._digest_cache.get(rel) if use_cache else None
            if cached and cached[0] == st.st_mtime_ns and cached[1] == st.st_size:
                sha = cached[2]
            else:
                sha = digest(p.read_bytes())
                self._digest_cache[rel] = (st.st_mtime_ns, st.st_size, sha)
            result[rel] = sha
        for stale in list(self._digest_cache):
            if stale not in result:
                del self._digest_cache[stale]
        return result


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
            if kind == "string":
                valid = isinstance(value, str)
            elif kind == "integer":
                valid = type(value) is int
            elif kind == "number":
                valid = type(value) in {int, float}
            elif kind == "boolean":
                valid = type(value) is bool
            elif kind == "array":
                valid = isinstance(value, list)
            elif kind == "object":
                valid = isinstance(value, dict)
            else:
                raise ToolError(f"不支持的参数类型声明：{kind}")
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


def register_workspace_tools(registry: Registry, deadline: float | None = None):
    workspace = registry.workspace

    def timeout(cap=60):
        remaining = min(cap, deadline - time.monotonic()) if deadline is not None else cap
        if remaining <= 0:
            raise ToolError("任务时间预算已用尽")
        return remaining

    def git_read(*args):
        try:
            result = subprocess.run(["git", "--no-optional-locks", "--literal-pathspecs", *args],
                cwd=workspace.root, capture_output=True, text=True, encoding="utf-8", errors="replace",
                timeout=timeout(15))
        except (OSError, subprocess.TimeoutExpired):
            raise ToolError("无法执行只读 Git 查询（Git 不可用或超时）") from None
        if result.returncode:
            raise ToolError("Git 查询失败；请确认工作区是具有所需版本历史的 Git 仓库")
        return result.stdout

    def git_path(path):
        if Path(git_read("rev-parse", "--show-toplevel").strip()).resolve() != workspace.root:
            raise ToolError("Git 工具要求工作区是仓库根目录")
        return workspace.path(path).relative_to(workspace.root).as_posix()

    def visible_path(path):
        try:
            workspace.path(path)
            return True
        except ToolError:
            return False

    def git_status(path="."):
        relative = git_path(path)
        raw = git_read("status", "--porcelain=v1", "-z", "--no-renames", "--untracked-files=all",
                       "--ignore-submodules=all", "--", relative)
        entries = [{"status": item[:2], "path": item[3:]} for item in raw.split("\0")
                   if len(item) > 3 and visible_path(item[3:])]
        return {"entries": entries[:200], "truncated": len(entries) > 200}

    def git_diff(path="."):
        relative = git_path(path)
        flags = ("--no-renames", "--no-ext-diff", "--no-textconv", "--ignore-submodules=all", "--no-color")
        raw = git_read("diff", "--name-only", "-z", *flags, "HEAD", "--", relative)
        files = [name for name in raw.split("\0") if name and visible_path(name)]
        if not files:
            return {"diff": "", "files": [], "truncated": False}
        # Explicit literal paths keep protected files out of the diff, including deleted files.
        selected = files[:100]
        diff = git_read("diff", *flags, "HEAD", "--", *selected)
        return {"diff": diff[:30000], "files": selected, "truncated": len(files) > 100 or len(diff) > 30000}

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
        if not target.exists():
            raise ToolError(f"文件不存在：{path}")
        if not target.is_file():
            raise ToolError(f"目标不是文件：{path}")
        if target.stat().st_size > 2_000_000:
            raise ToolError("文件超过 2MB，请缩小工作区或读取文本产物")
        raw = target.read_bytes()
        text = raw.decode("utf-8-sig")
        content = text.splitlines()
        return {"path": path, "sha256": digest(raw), "total_lines": len(content),
                "content": "\n".join(f"{i + 1}: {line}" for i, line in
                    enumerate(content[start_line - 1:start_line - 1 + lines], start_line - 1))}

    def match_glob(relative: Path, pattern: str) -> bool:
        if relative.match(pattern):
            return True
        if "**/" in pattern:
            collapsed = pattern
            while "**/" in collapsed:
                collapsed = collapsed.replace("**/", "", 1)
                if relative.match(collapsed):
                    return True
        return False

    def search(query, path=".", glob="*"):
        if not query:
            raise ToolError("搜索内容不能为空")
        matches = []
        for file in workspace.files(path):
            relative = file.relative_to(workspace.root)
            if not match_glob(relative, glob):
                continue
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

    def syntax_info(path: str, raw: bytes) -> dict:
        if not path.casefold().endswith(".py"):
            return {}
        try:
            ast.parse(raw, filename=path)
        except SyntaxError as exc:
            return {"syntax_valid": False, "syntax_error": {"line": exc.lineno, "message": exc.msg}}
        return {"syntax_valid": True}

    def check_syntax(path):
        target = workspace.path(path)
        if not target.is_file() or target.suffix != ".py" or target.stat().st_size > 2_000_000:
            raise ToolError("请选择不超过 2MB 的 Python 源文件")
        try:
            ast.parse(target.read_bytes(), filename=path)
        except SyntaxError as exc:
            return {"path": path, "valid": False, "line": exc.lineno, "message": exc.msg}
        return {"path": path, "valid": True}

    def edit_file(path, old_text, new_text, expected_sha256):
        target = workspace.path(path)
        if not target.exists():
            raise ToolError(f"文件不存在：{path}")
        if not target.is_file():
            raise ToolError(f"目标不是文件：{path}")
        raw = target.read_bytes()
        before_sha = digest(raw)
        if before_sha != expected_sha256:
            raise ToolError("文件已变化，请重新读取最新内容后再编辑")
        has_bom = raw.startswith(b"\xef\xbb\xbf")
        text = raw.decode("utf-8-sig")
        crlf = "\r\n" in text
        norm_text = text.replace("\r\n", "\n")
        norm_old = old_text.replace("\r\n", "\n")
        norm_new = new_text.replace("\r\n", "\n")
        if not norm_old or norm_text.count(norm_old) != 1:
            raise ToolError("old_text 必须精确匹配且只出现一次；请读取更明确的上下文")
        replaced = norm_text.replace(norm_old, norm_new, 1)
        if crlf:
            replaced = replaced.replace("\n", "\r\n")
        updated = replaced.encode("utf-8-sig" if has_bom else "utf-8")
        target.write_bytes(updated)
        after_sha = workspace._cache_digest(target, updated)
        return {"path": path, "before_sha256": before_sha, "after_sha256": after_sha, **syntax_info(path, updated)}

    def write_file(path, content):
        target = workspace.path(path)
        target.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation avoids overwriting a file created after the model read.
        try:
            with target.open("x", encoding="utf-8", newline="") as file:
                file.write(content)
        except FileExistsError:
            raise ToolError(f"文件已存在：{path}。修改已有文件请先调用 read_file 获取 sha256，再使用 edit_file。") from None
        raw = target.read_bytes()
        return {"path": path, "sha256": workspace._cache_digest(target, raw), **syntax_info(path, raw)}

    def run_tests(path="tests", runner="unittest"):
        target = workspace.path(path)
        if runner == "unittest":
            if target.is_dir():
                command = [sys.executable, "-m", "unittest", "discover", "-s", str(target), "-v"]
            elif target.is_file() and target.suffix == ".py":
                command = [sys.executable, "-m", "unittest", "discover", "-s", str(target.parent),
                           "-p", target.name, "-v"]
            else:
                raise ToolError("unittest 的 path 必须是测试目录或 Python 测试文件")
        else:
            command = [sys.executable, "-m", "pytest", str(target), "-q", "-p", "no:cacheprovider"]
        environment = dict(os.environ)
        for key in list(environment):
            if key.upper() in {"OPENAI_API_KEY", "CODEHARNESS_API_KEY", "DASHSCOPE_API_KEY"}:
                environment.pop(key)
        environment["PYTHONDONTWRITEBYTECODE"] = "1"
        environment["PYTHONIOENCODING"] = "utf-8"
        test_timeout = timeout()
        process = subprocess.Popen(command, cwd=workspace.root, env=environment,
                                   stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        try:
            output, _ = process.communicate(timeout=test_timeout)
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
            "query": string("搜索文本"), "path": string("相对目录或文件"),
            "glob": string("可选路径匹配规则，例如 *.py 或 app/*.py")}, ["query"]), search),
        Tool("check_syntax", "检查 Python 文件语法，不执行代码也不阻止编辑。", parameters({"path": string("相对 Python 文件路径")}, ["path"]), check_syntax),
        Tool("edit_file", "精确替换一次文本，sha256 必须来自最新读取。", parameters({
            "path": string("相对文件路径"), "old_text": string("唯一匹配的原文本"),
            "new_text": string("替换文本"), "expected_sha256": string("最新文件摘要")},
            ["path", "old_text", "new_text", "expected_sha256"]), edit_file, "write"),
        Tool("write_file", "仅用于创建尚不存在的新文件；修改已有文件必须使用 edit_file。", parameters({
            "path": string("相对文件路径"), "content": string("文件内容")}, ["path", "content"]), write_file, "write"),
        Tool("run_tests", "在工作区运行测试，最多 60 秒；会执行项目代码，需要执行授权。", parameters({
            "path": string("测试目录或测试文件，默认 tests"),
            "runner": {"type": "string", "enum": ["unittest", "pytest"]}}), run_tests, "execute"),
    ]:
        registry.register(tool)

    if (workspace.root / ".git").exists():
        path_parameter = parameters({"path": string("相对目录或文件")})
        registry.register(Tool("git_status", "只读列出 Git 工作区改动，不包含受保护路径。", path_parameter, git_status))
        registry.register(Tool("git_diff", "只读查看相对 HEAD 的已跟踪文件差异，不包含受保护路径。", path_parameter, git_diff))

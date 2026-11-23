"""Tools share path checks and a policy gate. Hooks cannot bypass that gate."""

from dataclasses import dataclass
import ast
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
import tempfile
import time
from typing import Callable


class ToolError(RuntimeError):
    pass


HIDDEN = {".git", ".venv", "venv", ".idea", ".codeharness", ".ssh", ".aws", "node_modules", "__pycache__"}
PRIVATE_FILENAMES = {".netrc", ".pypirc", ".npmrc", ".git-credentials"}
WALK_IGNORED = {"dist", "build", "target", ".tox", ".mypy_cache", ".pytest_cache", ".ruff_cache", "htmlcov", ".next"}
TEST_ENV_NAMES = {
    "PATH", "PATHEXT", "SYSTEMROOT", "SYSTEMDRIVE", "WINDIR", "COMSPEC", "TEMP", "TMP", "TMPDIR",
    "HOME", "USERPROFILE", "APPDATA", "LOCALAPPDATA", "LANG", "PYTHONPATH", "VIRTUAL_ENV", "CONDA_PREFIX",
}


def protected(name: str) -> bool:
    name = name.casefold()
    return (name in HIDDEN or name in PRIVATE_FILENAMES or
            name.startswith((".env", "id_rsa", "id_ed25519", ".codeharness-patch-"))
            or name.endswith((".pem", ".key", ".p12")))


def test_subprocess_env(pass_env: tuple[str, ...] = ()) -> dict[str, str]:
    env = {name: value for name, value in os.environ.items()
           if name.upper() in TEST_ENV_NAMES or name.upper().startswith("LC_")}
    env.update({name: os.environ[name] for name in pass_env if name in os.environ})
    env.update(PYTHONDONTWRITEBYTECODE="1", PYTHONIOENCODING="utf-8")
    return env


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
        indexed = self._git_files(start)
        if indexed is not None:
            yield from indexed
            return
        if start.is_file():
            yield start
            return
        for current, dirs, names in os.walk(start):
            dirs[:] = sorted(d for d in dirs if not protected(d) and d.casefold() not in WALK_IGNORED
                             and not (Path(current) / d).is_symlink())
            for filename in sorted(names):
                file = Path(current) / filename
                if not protected(filename) and not file.is_symlink():
                    yield self.path(str(file.relative_to(self.root)))

    def _git_files(self, start: Path):
        if not (self.root / ".git").exists():
            return None
        try:
            result = subprocess.run(["git", "--no-optional-locks", "--literal-pathspecs", "ls-files", "-z",
                "--cached", "--others", "--exclude-standard", "--", start.relative_to(self.root).as_posix()],
                cwd=self.root, capture_output=True, timeout=15)
        except (OSError, subprocess.TimeoutExpired):
            return None
        if result.returncode:
            return None
        names = {Path(os.fsdecode(item)) for item in result.stdout.split(b"\0") if item}
        visible = []
        for relative in sorted(names, key=lambda path: (path.parts[:-1], path.name)):
            if (self.root / relative).is_symlink():
                continue
            try:
                target = self.path(relative.as_posix())
            except ToolError:
                continue
            if target.is_file():
                visible.append(target)
        return visible

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


def parse_unified_patch(patch: str):
    lines = patch.replace("\r\n", "\n").splitlines(keepends=True)
    last = next((i for i in range(len(lines) - 1, -1, -1) if lines[i].strip()), None)
    if last is not None and lines[last].rstrip("\n") == "*** End Patch":
        lines = lines[:last]
    metadata = ("diff --git ", "index ", "new file mode ", "deleted file mode ")
    index = 0
    while index < len(lines):
        if not lines[index].strip() or lines[index].startswith(metadata):
            index += 1
            continue
        if index + 1 >= len(lines) or not lines[index].startswith("--- ") or not lines[index + 1].startswith("+++ "):
            raise ToolError(f"补丁第 {index + 1} 行缺少成对的文件头")
        old = lines[index][4:].rstrip("\n").split("\t", 1)[0]
        new = lines[index + 1][4:].rstrip("\n").split("\t", 1)[0]
        if old.startswith("a/") and (new.startswith("b/") or new == "/dev/null"):
            old = old[2:]
        if new.startswith("b/") and (old == "/dev/null" or old == new[2:]):
            new = new[2:]
        if not old or not new or (old != new and "/dev/null" not in (old, new)) or old == new == "/dev/null":
            raise ToolError("文件头必须指向同一文件，新增或删除用 /dev/null")
        index += 2
        hunks = []
        while index < len(lines) and lines[index].startswith("@@"):
            head = lines[index].rstrip("\n")
            header = re.fullmatch(r"@@ -(\d+)(?:,(\d+))? \+\d+(?:,(\d+))? @@.*", head)
            if header is None and head != "@@":
                raise ToolError(f"{old} 的补丁片段头无效")
            offset = before_count = after_count = 0
            if header:
                offset, before_count, after_count = (int(part) if part is not None else 1 for part in header.groups())
            index += 1
            before, after = [], []
            while index < len(lines):
                raw = lines[index]
                if header:
                    if len(before) >= before_count and len(after) >= after_count:
                        break
                elif (raw.startswith(("@@", *metadata))
                      or (raw.startswith("--- ") and index + 2 < len(lines)
                          and lines[index + 1].startswith("+++ ") and lines[index + 2].startswith("@@"))):
                    break
                if raw == "\n":
                    raw = " \n"
                sign, line = raw[0], raw[1:]
                if sign not in {" ", "+", "-"}:
                    raise ToolError(f"{old} 的补丁片段行数与声明不符")
                index += 1
                if index < len(lines) and lines[index].rstrip("\n") == "\\ No newline at end of file":
                    line = line.removesuffix("\n")
                    index += 1
                elif not line.endswith("\n"):
                    line += "\n"
                if sign != "+":
                    before.append(line)
                if sign != "-":
                    after.append(line)
            if header and (len(before) != before_count or len(after) != after_count or not (before or after)):
                raise ToolError(f"{old} 的补丁片段行数无效")
            if not header and not before:
                raise ToolError(f"{old} 的无行号片段须包含可唯一匹配的原文；纯插入请使用带行号的片段")
            hunks.append((offset, before, after))
        if not hunks:
            raise ToolError(f"{old} 没有补丁片段")
        yield old, new, hunks


def patch_text(path: str, text: str, hunks) -> str:
    lines = text.replace("\r\n", "\n").splitlines(keepends=True)
    shift = 0
    for number, (offset, old, new) in enumerate(hunks, 1):
        if old:
            positions = [i for i, line in enumerate(lines) if line == old[0] and lines[i:i + len(old)] == old]
            if len(positions) != 1:
                raise ToolError(f"{path} 的第 {number} 个片段原文必须唯一匹配")
            position = positions[0]
        else:
            position = offset + shift
            if not 0 <= position <= len(lines):
                raise ToolError(f"{path} 的第 {number} 个插入位置无效")
        lines[position:position + len(old)] = new
        shift += len(new) - len(old)
    updated = "".join(lines)
    return updated.replace("\n", "\r\n") if "\r\n" in text else updated


def replace_patch_files(updates):
    staged, applied = [], []
    temporary = []

    def stage(path, content, mode):
        if content is None:
            return None
        with tempfile.NamedTemporaryFile(dir=path.parent, prefix=".codeharness-patch-", delete=False) as stream:
            temp = Path(stream.name)
            temporary.append(temp)
            stream.write(content)
        temp.chmod(mode)
        return temp

    try:
        for _, path, before, after in updates:
            path.parent.mkdir(parents=True, exist_ok=True)
            mode = path.stat().st_mode & 0o777 if before is not None else 0o644
            staged.append((path, before, stage(path, before, mode), stage(path, after, mode)))
        for path, before, backup, after in staged:
            current = path.read_bytes() if path.exists() else None
            if current != before:
                raise ToolError(f"补丁验证后文件已变化：{path.name}")
            if after is None:
                path.unlink()
            elif before is None:
                try:
                    os.link(after, path)
                except FileExistsError:
                    raise
                except OSError:
                    with path.open("xb") as stream:
                        applied.append((path, backup))
                        stream.write(after.read_bytes())
                    path.chmod(after.stat().st_mode & 0o777)
                    continue
            else:
                os.replace(after, path)
            applied.append((path, backup))
    except (OSError, ToolError):
        for path, backup in reversed(applied):
            if backup is None:
                path.unlink()
            else:
                os.replace(backup, path)
        raise
    finally:
        for path in temporary:
            path.unlink(missing_ok=True)


@dataclass
class Tool:
    name: str
    description: str
    parameters: dict
    execute: Callable
    effect: str = "read"
    parallel_safe: bool = False

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
    def __init__(self, allow_write=False, allow_exec=False, readonly=False, confirm: Callable | None = None,
                 *, pass_env: tuple[str, ...] = ()):
        self.allow_write = allow_write
        self.allow_exec = allow_exec
        self.readonly = readonly
        self.confirm = confirm
        self.pass_env = pass_env

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

    def search(query, path=".", glob="*", regex=False, max_results=40):
        if not query:
            raise ToolError("搜索内容不能为空")
        if not 1 <= max_results <= 200:
            raise ToolError("max_results 应在 1 到 200 之间")
        pattern = None
        if regex:
            if len(query) > 200:
                raise ToolError("正则搜索模式不能超过 200 字符")
            try:
                pattern = re.compile(query, re.IGNORECASE)
            except re.error as exc:
                raise ToolError(f"无效的正则表达式：{exc}") from None
        files = [file for file in workspace.files(path)
                 if match_glob(file.relative_to(workspace.root), glob) and file.stat().st_size <= 2_000_000]
        rg = shutil.which("rg") if pattern is not None else None
        folded_query = query.casefold()
        matches = []
        for start in range(0, len(files), 16):
            batch = files[start:start + 16]
            found = ripgrep_search(rg, query, batch, max_results) if rg else None
            if found is None:
                found = python_search(batch, pattern.search if pattern else lambda line: folded_query in line.casefold())
            for match in found:
                matches.append(match)
                if len(matches) >= max_results:
                    return {"matches": matches, "truncated": True}
        return {"matches": matches, "truncated": False}

    def python_search(files, matches_line):
        for file in files:
            try:
                lines = file.read_text(encoding="utf-8-sig").splitlines()
            except (OSError, UnicodeError):
                continue
            relative = file.relative_to(workspace.root).as_posix()
            yield from ({"path": relative, "line": number, "text": line[:400]}
                        for number, line in enumerate(lines, 1) if matches_line(line))

    def ripgrep_search(rg, query, files, limit):
        paths = [file.relative_to(workspace.root).as_posix() for file in files]
        try:
            process = subprocess.run([rg, "--no-config", "--hidden", "--no-ignore", "--json", "--ignore-case",
                "--max-count", str(limit), "-e", query, "--", *paths], cwd=workspace.root, capture_output=True,
                encoding="utf-8", timeout=timeout(15))
        except (OSError, UnicodeError, subprocess.TimeoutExpired):
            return None
        if process.returncode not in (0, 1):
            return None
        found = {path: [] for path in paths}
        for line in process.stdout.splitlines():
            item = json.loads(line)
            if item["type"] == "match":
                data = item["data"]
                relative = data["path"].get("text", "").replace("\\", "/")
                if relative in found and "text" in data["lines"]:
                    found[relative].append({"path": relative, "line": data["line_number"],
                        "text": data["lines"]["text"].rstrip("\r\n")[:400]})
        return [match for path in paths for match in found[path]]

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

    def apply_patch(patch):
        updates = []
        seen = set()
        for old, new, hunks in parse_unified_patch(patch):
            path = new if new != "/dev/null" else old
            target = workspace.path(path)
            if target in seen:
                raise ToolError(f"补丁重复指定文件：{path}")
            seen.add(target)
            exists = target.exists()
            if exists != (old != "/dev/null") or (exists and not target.is_file()):
                raise ToolError(f"补丁文件头与磁盘状态不符：{path}")
            before = target.read_bytes() if exists else None
            text = before.decode("utf-8-sig") if before is not None else ""
            fixed = patch_text(path, text, hunks)
            if new == "/dev/null" and fixed:
                raise ToolError(f"删除片段未覆盖整个文件：{path}")
            encoding = "utf-8-sig" if before and before.startswith(b"\xef\xbb\xbf") else "utf-8"
            after = None if new == "/dev/null" else fixed.encode(encoding)
            updates.append((path, target, before, after))
        if not updates:
            raise ToolError("补丁不能为空")
        replace_patch_files(updates)
        return {"files": [{"path": path, "before_sha256": digest(before) if before is not None else None,
            "after_sha256": workspace._cache_digest(target, after) if after is not None else None,
            **(syntax_info(path, after) if after is not None else {})} for path, target, before, after in updates]}

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
        environment = test_subprocess_env(registry.policy.pass_env)
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
        Tool("search", "搜索代码，返回路径、行号和匹配片段。", parameters({
            "query": string("搜索文本"), "path": string("相对目录或文件"),
            "glob": string("可选路径匹配规则，例如 *.py 或 app/*.py"),
            "regex": {"type": "boolean", "description": "是否按正则表达式搜索，默认按字面"},
            "max_results": integer("返回数量上限，默认 40，上限 200")}, ["query"]), search),
        Tool("check_syntax", "检查 Python 文件语法，不执行代码也不阻止编辑。", parameters({"path": string("相对 Python 文件路径")}, ["path"]), check_syntax),
        Tool("edit_file", "精确替换一次文本，sha256 必须来自最新读取。", parameters({
            "path": string("相对文件路径"), "old_text": string("唯一匹配的原文本"),
            "new_text": string("替换文本"), "expected_sha256": string("最新文件摘要")},
            ["path", "old_text", "new_text", "expected_sha256"]), edit_file, "write"),
        Tool("write_file", "仅用于创建尚不存在的新文件；修改已有文件必须使用 edit_file。", parameters({
            "path": string("相对文件路径"), "content": string("文件内容")}, ["path", "content"]), write_file, "write"),
        Tool("apply_patch", "一次修改多处。先读取原文，每个片段必须唯一匹配；失败时可改用 edit_file。",
             parameters({"patch": string("每个文件用 --- 路径、+++ 路径。已有原文的修改优先使用独立的 @@ 行，"
                                           "然后写带前缀的正文：空格为上下文，- 删除，+ 新增。"
                                           "例如 --- a.py\n+++ a.py\n@@\n-old = 1\n+old = 2\n。"
                                           "纯插入或新建使用带起点和行数的标准统一 diff。")}, ["patch"]), apply_patch, "write"),
        Tool("run_tests", "在工作区运行测试，最多 60 秒；会执行项目代码，需要执行授权。", parameters({
            "path": string("测试目录或测试文件，默认 tests"),
            "runner": {"type": "string", "enum": ["unittest", "pytest"]}}), run_tests, "execute"),
    ]:
        registry.register(tool)

    if (workspace.root / ".git").exists():
        path_parameter = parameters({"path": string("相对目录或文件")})
        registry.register(Tool("git_status", "只读列出 Git 工作区改动，不包含受保护路径。", path_parameter, git_status))
        registry.register(Tool("git_diff", "只读查看相对 HEAD 的已跟踪文件差异，不包含受保护路径。", path_parameter, git_diff))
    for name in ("list_files", "read_file", "search", "check_syntax", "git_status", "git_diff"):
        if name in registry.tools:
            registry.tools[name].parallel_safe = True

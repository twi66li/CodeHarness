"""Pi-inspired in-process extension API with lifecycle hooks, tools, and slash commands."""

from dataclasses import dataclass
import importlib.util
from pathlib import Path
from typing import Callable

from .tools import Registry, Tool

LIFECYCLE_EVENTS = (
    "session_start",
    "before_context",
    "before_tool",
    "after_tool",
    "before_compact",
    "session_end",
)


@dataclass
class SlashCommand:
    name: str
    description: str
    handler: Callable


class ExtensionAPI:
    def __init__(self, host: "ExtensionHost", workspace: Path, store):
        self._host = host
        self.workspace = workspace
        self.store = store

    def register_tool(self, tool: Tool):
        self._host.tools.append(tool)

    def register_command(self, name: str, description: str, handler: Callable):
        clean = name.strip().lstrip("/").lower()
        if not clean or any(ch.isspace() for ch in clean):
            raise ValueError(f"无效的斜杠命令名：{name}")
        self._host.commands[clean] = SlashCommand(clean, description, handler)

    def on(self, event: str, handler: Callable):
        if event not in LIFECYCLE_EVENTS:
            raise ValueError(f"未知生命周期事件：{event}；可选：{', '.join(LIFECYCLE_EVENTS)}")
        self._host.handlers[event].append(handler)


class ExtensionHost:
    def __init__(self, workspace: Path, store):
        self.workspace = workspace.resolve()
        self.store = store
        self.tools: list[Tool] = []
        self.commands: dict[str, SlashCommand] = {}
        self.handlers: dict[str, list[Callable]] = {event: [] for event in LIFECYCLE_EVENTS}
        self.legacy_registrars: list[Callable] = []
        self._loaded_paths: set[Path] = set()
        self._seq = 0

    def api(self) -> ExtensionAPI:
        return ExtensionAPI(self, self.workspace, self.store)

    def register_builtin(self, setup_fn: Callable[[ExtensionAPI], None]):
        setup_fn(self.api())

    def load_file(self, path: Path):
        resolved = path.resolve()
        if resolved in self._loaded_paths:
            return
        self._seq += 1
        spec = importlib.util.spec_from_file_location(f"codeharness_extension_{self._seq}", resolved)
        if not spec or not spec.loader:
            raise ValueError(f"无法加载扩展：{path}")
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        setup = getattr(module, "setup", None)
        register = getattr(module, "register", None)
        if callable(setup):
            setup(self.api())
        elif callable(register):
            self.legacy_registrars.append(register)
        else:
            raise ValueError(f"扩展缺少 setup(api) 或 register(registry) 入口：{path}")
        self._loaded_paths.add(resolved)

    def discover(self, workspace: Path | None = None):
        root = (workspace or self.workspace).resolve()
        ext_dir = root / ".codeharness" / "extensions"
        if not ext_dir.is_dir() or not ext_dir.resolve().is_relative_to(root):
            return
        for file in sorted(ext_dir.glob("*.py")):
            if file.name.startswith("_") or not file.resolve().is_relative_to(ext_dir.resolve()):
                continue
            self.load_file(file)

    def apply_to_registry(self, registry: Registry, *, include_tools: bool = True):
        if include_tools:
            for tool in self.tools:
                if tool.name not in registry.tools:
                    registry.register(tool)
            for registrar in self.legacy_registrars:
                registrar(registry)
        if self.handlers["before_tool"]:
            def before_adapter(name: str, args: dict):
                for handler in self.handlers["before_tool"]:
                    reason = handler({"name": name, "arguments": args})
                    if reason:
                        return str(reason)
                return None

            registry.before.append(before_adapter)
        if self.handlers["after_tool"]:
            def after_adapter(name: str, args: dict, result: dict):
                for handler in self.handlers["after_tool"]:
                    handler({"name": name, "arguments": args, "result": result})

            registry.after.append(after_adapter)

    def emit(self, event: str, payload: dict) -> list:
        results = []
        for handler in self.handlers.get(event, ()):
            value = handler(payload)
            if value is not None:
                results.append(value)
        return results

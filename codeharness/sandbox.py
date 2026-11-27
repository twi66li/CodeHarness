"""Optional container sandbox executor for run_tests and bash (stdlib only)."""

from dataclasses import dataclass
import os
from pathlib import Path
import re
import subprocess
from typing import Protocol
import uuid


@dataclass(frozen=True)
class ExecResult:
    exit_code: int
    output: str


class Executor(Protocol):
    mode: str

    def python_executable(self) -> str: ...

    def format_path(self, target: Path, workspace_root: Path) -> str: ...

    def run_argv(self, argv: list[str], cwd: Path, env: dict[str, str], timeout: float,
                 *, pass_env: tuple[str, ...] = ()) -> ExecResult: ...

    def run_shell(self, command: str, cwd: Path, env: dict[str, str], timeout: float,
                  *, pass_env: tuple[str, ...] = ()) -> ExecResult: ...


def _valid_token(value: str, label: str) -> str:
    text = value.strip()
    if not text or any(ch.isspace() for ch in text):
        raise ValueError(f"{label} 不能为空且不能包含空白字符")
    return text


class DockerExecutor:
    """Run commands inside an ephemeral, network-isolated, resource-capped Docker container."""

    mode = "docker"

    def __init__(self, image: str = "python:3.12-slim", *, memory: str = "512m",
                 cpus: str = "1", pids_limit: int = 64, network: str = "none"):
        self.image = _valid_token(image, "sandbox image")
        self.memory = _valid_token(memory, "sandbox memory")
        self.cpus = _valid_token(cpus, "sandbox cpus")
        self.network = _valid_token(network, "sandbox network")
        if type(pids_limit) is not int or pids_limit < 1:
            raise ValueError("pids_limit 必须是正整数")
        if not re.fullmatch(r"[0-9]+(\.[0-9]+)?", self.cpus):
            raise ValueError("sandbox cpus 必须是正数")
        self.pids_limit = pids_limit

    def python_executable(self) -> str:
        return "python"

    def format_path(self, target: Path, workspace_root: Path) -> str:
        rel = target.resolve().relative_to(workspace_root.resolve()).as_posix()
        return rel or "."

    def container_env(self, env: dict[str, str], pass_env: tuple[str, ...]) -> dict[str, str]:
        selected = {
            "HOME": "/tmp",
            "PYTHONDONTWRITEBYTECODE": "1",
            "PYTHONIOENCODING": "utf-8",
        }
        for name in pass_env:
            if name in env:
                selected[name] = env[name]
        return selected

    def build_command(self, inner_argv: list[str], cwd: Path, env: dict[str, str],
                      container_name: str, *, pass_env: tuple[str, ...] = ()) -> list[str]:
        cmd = [
            "docker", "run", "--rm", "--init",
            "--name", container_name,
            "--network", self.network,
            "--memory", self.memory,
            "--cpus", self.cpus,
            "--pids-limit", str(self.pids_limit),
            "--read-only",
            "--tmpfs", "/tmp:rw,nosuid,nodev,size=64m",
            "--cap-drop", "ALL",
            "--security-opt", "no-new-privileges",
            "-w", "/workspace",
            "-v", f"{cwd.resolve()}:/workspace:rw",
        ]
        if hasattr(os, "getuid") and hasattr(os, "getgid"):
            cmd.extend(["--user", f"{os.getuid()}:{os.getgid()}"])
        for key, value in self.container_env(env, pass_env).items():
            cmd.extend(["-e", f"{key}={value}"])
        cmd.append(self.image)
        cmd.extend(inner_argv)
        return cmd

    def _run(self, inner_argv: list[str], cwd: Path, env: dict[str, str], timeout: float,
             pass_env: tuple[str, ...]) -> ExecResult:
        name = f"codeharness-{uuid.uuid4().hex[:12]}"
        cmd = self.build_command(inner_argv, cwd, env, name, pass_env=pass_env)
        try:
            process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        except FileNotFoundError as exc:
            raise RuntimeError("未检测到 docker 命令，请安装并启动 Docker，或改用 --sandbox local") from exc
        try:
            output, _ = process.communicate(timeout=timeout)
        except (subprocess.TimeoutExpired, KeyboardInterrupt):
            try:
                subprocess.run(["docker", "rm", "-f", name], capture_output=True, timeout=10)
            except (OSError, subprocess.SubprocessError):
                pass
            process.kill()
            process.communicate()
            raise
        return ExecResult(process.returncode, output.decode("utf-8", errors="replace"))

    def run_argv(self, argv: list[str], cwd: Path, env: dict[str, str], timeout: float,
                 *, pass_env: tuple[str, ...] = ()) -> ExecResult:
        return self._run(argv, cwd, env, timeout, pass_env)

    def run_shell(self, command: str, cwd: Path, env: dict[str, str], timeout: float,
                  *, pass_env: tuple[str, ...] = ()) -> ExecResult:
        return self._run(["sh", "-c", command], cwd, env, timeout, pass_env)

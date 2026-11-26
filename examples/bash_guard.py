"""Example Pi-style extension: block destructive bash commands via before_tool hook."""

import re

BLOCKED_PATTERNS = (
    (re.compile(r"\brm\s+-[a-zA-Z]*r[a-zA-Z]*f|\brm\s+-[a-zA-Z]*f[a-zA-Z]*r"), "禁止执行 rm -rf 批量删除命令"),
    (re.compile(r"\bgit\s+push\b.*(--force|-f\b)"), "禁止强制推送 git push --force"),
    (re.compile(r"\b(mkfs|shutdown|reboot)\b"), "禁止执行系统破坏或关机命令"),
)


def setup(api):
    def guard(event):
        if event["name"] != "bash":
            return None
        command = str(event["arguments"].get("command", ""))
        for pattern, reason in BLOCKED_PATTERNS:
            if pattern.search(command):
                return f"bash_guard 拦截：{reason}"
        return None

    api.on("before_tool", guard)

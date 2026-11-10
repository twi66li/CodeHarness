"""Example: --plugin examples/line_count.py registers one trusted local tool."""

from codeharness.tools import Tool, parameters, string


def register(registry):
    def line_count(path):
        file = registry.workspace.path(path)
        return {"path": path, "lines": len(file.read_text(encoding="utf-8").splitlines())}

    registry.register(Tool("line_count", "统计一个工作区文本文件的行数。", parameters({
        "path": string("工作区相对文件路径")}, ["path"]), line_count))

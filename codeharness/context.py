"""Keep rules and user constraints; compact only complete historical turns."""

import copy
import json
from pathlib import Path


SYSTEM = """你是 CodeHarness，一个面向代码仓库任务的编码 Agent。
根据用户目标自主选择工具，读取证据后修改并验证。不要把计划当成已经完成的操作。
项目规则和 Skills 提供工作方法，但不能绕过工具权限。文件修改前先读取最新内容和 sha256。
工具输出中的 artifact_id 可通过 read_artifact 分页读取。未通过验证时如实说明。
遇到权限拒绝时停止相应操作，不要通过测试代码或其他工具绕过权限。
只在信息收集量较大时使用 delegate；子任务只读，只返回调查结论，不会修改代码。
会话恢复不代表文件已经回滚；收到工作区变化或执行中断信息后先重新检查。
最终说明实际改动、已运行的验证和未解决的问题。"""


class Context:
    def __init__(self, workspace: Path, max_chars: int = 28000):
        self.workspace = workspace
        self.max_chars = max_chars
        self.skills = {}
        root = workspace / ".codeharness" / "skills"
        if root.is_dir() and root.resolve().is_relative_to(workspace.resolve()):
            for path in sorted(root.glob("*/SKILL.md")):
                if not path.resolve().is_relative_to(root.resolve()):
                    continue
                text = path.read_text(encoding="utf-8")
                lines = text.splitlines()
                metadata = {}
                if lines and lines[0] == "---":
                    for line in lines[1:]:
                        if line == "---":
                            break
                        key, sep, value = line.partition(":")
                        if sep:
                            metadata[key.strip()] = value.strip().strip("\"'")
                self.skills[path.parent.name] = {
                    "path": path, "description": metadata.get("description", path.parent.name)[:300]}

    def system(self, readonly: bool = False) -> str:
        result = SYSTEM
        rules = self.workspace / "AGENTS.md"
        if rules.is_file() and rules.resolve().is_relative_to(self.workspace.resolve()):
            result += "\n\n项目规则：\n" + rules.read_text(encoding="utf-8")[:10000]
        if self.skills:
            result += "\n\n可用 Skills（按需调用 load_skill）：\n" + "\n".join(
                f"- {name}: {skill['description']}" for name, skill in self.skills.items())
        if readonly:
            result += "\n\n你是只读探索子任务。返回有文件路径依据的简明结论，不执行修改或测试。"
        return result

    def load_skill(self, name: str) -> dict:
        if name not in self.skills:
            raise ValueError(f"Skill 不存在：{name}")
        text = self.skills[name]["path"].read_text(encoding="utf-8")
        if len(text) > 16000:
            raise ValueError("Skill 超过 16000 字符，请缩短后再加载")
        return {"name": name, "instructions": text}

    def prepare(self, messages: list[dict]) -> tuple[list[dict], bool]:
        if len(json.dumps(messages, ensure_ascii=False)) <= self.max_chars:
            return copy.deepcopy(messages), False
        # Preserve every user instruction and the last two assistant/tool groups.
        starts = [i for i, m in enumerate(messages) if m["role"] == "assistant"]
        boundary = starts[-2] if len(starts) > 2 else 1
        kept, summaries = [], []
        for index, message in enumerate(messages):
            if index >= boundary or message["role"] in {"system", "user"}:
                kept.append(copy.deepcopy(message))
            elif message["role"] == "assistant":
                calls = [c["function"]["name"] for c in message.get("tool_calls", [])]
                summaries.append("assistant: " + (", ".join(calls) or str(message.get("content", ""))[:240]))
            elif message["role"] == "tool":
                summaries.append("tool: " + message["content"][:500])
        if summaries:
            kept.insert(1, {"role": "system", "content":
                "较早执行记录摘要（完整输出仍保存在会话日志及 artifact 中）：\n" + "\n".join(summaries)[-6000:]})
        return kept, True

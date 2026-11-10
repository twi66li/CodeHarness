# CodeHarness

使用 Python 实现的可扩展编码 Agent 运行时。Python 3.11+，运行时仅使用标准库。

## 运行

```powershell
python -m codeharness demo
python -m unittest discover -s tests -v
```

`demo` 在新建目录里演示：只读委派 → 定位 → 失败测试 → 修改 → 验证。
它使用确定性适配器，不调用真实 AI，结果不代表模型修复成功率。

接入支持原生工具调用的 Chat Completions 兼容接口：将 `.env.example` 的配置填入本地 `.env`。

```powershell
python -m codeharness run "给项目增加一个功能并验证" --workspace D:/your/repo --env-file .env
```

默认逐次询问写入和测试执行权限。非交互环境需要显式传入 `--allow-write`、`--allow-exec`。
`--isolate` 从干净 Git 仓库的 HEAD 创建独立 worktree，修改结果保留供检查。

```powershell
python -m codeharness sessions --workspace D:/your/repo
python -m codeharness resume SESSION_ID --workspace D:/your/repo --env-file .env
python -m codeharness trace SESSION_ID --workspace D:/your/repo --json
```

## 首版机制

- 主任务和只读探索子任务共用执行循环、请求与 Token 预算；子任务独立上下文，最多 6 次请求。
- 工具统一注册并声明权限。编辑校验 SHA-256，拒绝过期内容及工作区外路径。
- SQLite 追加记录模型输入、工具结果、用量和状态；长输出保存在产物中，可按页读取。
- 恢复时补全中断的工具结果并核对文件变化，不自动重放结果未知的写操作。
- 上下文超出阈值后压缩较早的完整回合，保留所有用户消息及最近回合；这不是语义摘要。
- 项目根目录 `AGENTS.md` 提供规则；`.codeharness/skills/<name>/SKILL.md` 的正文按需加载。
  Skill 可用 `---` 包裹 `description: 简短说明`，目录名作为调用名称。
- `--plugin examples/line_count.py` 演示可信 Python 工具扩展；注册表也提供 `before` / `after` 回调。

`verified` 仅表示当前工作区最后一次测试命令通过，不能替代独立功能验收。
Token 预算在请求前估算、返回后按 usage 校正，不是供应商侧的硬计费限额。
时间预算在调用边界检查；模型请求最多 60 秒，单次测试最多 60 秒。
测试在本机执行；路径检查、权限和 Git worktree 不构成操作系统沙箱。
扩展是可信本地 Python 代码，拥有宿主权限；只读子任务不加载自定义扩展。
当前不提供任意 Shell、并行写入或第三方插件兼容性。

设计参考：[Pi](https://github.com/earendil-works/pi)、
[Claude Code 公开文档](https://code.claude.com/docs/en/how-claude-code-works)、
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)、
[oh-my-pi](https://github.com/can1357/oh-my-pi)。本项目用 Python 独立实现，未复制其运行时代码。

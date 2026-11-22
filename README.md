# CodeHarness

[![CI](https://github.com/twi66li/CodeHarness/actions/workflows/ci.yml/badge.svg)](https://github.com/twi66li/CodeHarness/actions/workflows/ci.yml)

使用 Python 实现的可扩展编码 Agent 运行时。Python 3.11+，运行时仅使用标准库。

[English](README.en.md)

## 架构

```mermaid
flowchart LR
    CLI["cli.py<br/>run / resume / demo / sessions / trace"] --> Agent
    Bench["benchmark.py<br/>fixtures / model 评测"] --> Agent
    Bench --> Accept["独立验收脚本<br/>位于 Agent 工作区之外"]

    subgraph Agent["runtime.Agent 统一执行循环"]
        direction TB
        Budget["请求 / Token / 时间预算检查"] --> Prepare["Context.prepare<br/>保留用户消息与最近回合"]
        Prepare --> Call["Model.complete<br/>有限重试与退避"]
        Call --> Batch["执行 tool_calls 批次"]
        Batch --> Check["checkpoint / verification"]
        Check --> Budget
    end

    Call --> Model["models.ChatModel<br/>Chat Completions 兼容"]
    Prepare --> Ctx["context.Context<br/>AGENTS.md · Skills · 压缩"]
    Batch --> Reg["tools.Registry<br/>schema 校验 → before 钩子 → Policy → 执行 → after 钩子"]
    Reg --> WS["tools.Workspace<br/>路径边界 · 受保护文件 · sha256 快照"]
    Batch -- delegate --> Child["只读子任务<br/>同一循环 · 独立上下文 · 共享 root 预算 · ≤6 次请求"]
    Agent --> Store[("store.Store · SQLite<br/>sessions · 追加事件 · artifacts")]
    Store -. resume / repair_pending .-> Agent
```

| 模块 | 职责 |
| --- | --- |
| `runtime.py` | 执行循环、预算与超时、重试、工具批次、只读委派、最终状态与验证判定 |
| `models.py` | 模型接口协议与 Chat Completions 适配，错误分类、`Retry-After`、响应清洗 |
| `tools.py` | 工作区路径边界、权限策略、工具注册与参数校验、内置文件/搜索/测试/Git 工具 |
| `context.py` | 系统提示、`AGENTS.md` 与 Skills 加载、超阈值时的历史回合压缩 |
| `store.py` | SQLite 追加事件、产物分页、用量汇总、中断工具调用的补全 |
| `benchmark.py` / `benchmark_tasks.py` | 独立验收评测、委派消融、业务夹具 |

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
使用 `--no-delegate` 可以关闭探索子任务；使用 `--model-attempts` 调整单轮模型最大尝试次数（默认 3，含首次请求）。

```powershell
python -m codeharness sessions --workspace D:/your/repo
python -m codeharness resume SESSION_ID --workspace D:/your/repo --env-file .env
python -m codeharness trace SESSION_ID --workspace D:/your/repo --json
```

## 运行机制

- 主任务和只读探索子任务共用执行循环、请求与 Token 预算；子任务独立上下文，最多 6 次请求。
- 模型请求与重试共享预算；429、常见临时 5xx 和可重试连接错误有限重试，遵循 `Retry-After` 或指数退避。权限与认证拒绝终止当前任务，不自动绕过。
- 工具统一注册并声明权限。编辑校验 SHA-256，拒绝过期内容及工作区外路径；写入或编辑 `.py` 文件时附带非阻塞语法诊断。
- 支持按 glob（含 `**/`）搜索、单文件 `unittest` 和非执行式 `check_syntax`。Git 仓库根目录提供只读 `git_status` 和 `git_diff`，差异相对 HEAD，仅包含可见的已跟踪文件，输出过长时可缩小路径。
- SQLite 追加记录模型输入、工具结果、用量和状态；长输出保存在产物中，可按页读取。
- 恢复时补全中断的工具结果并核对文件变化，不自动重放结果未知的写操作。
- 上下文超出阈值后压缩较早的完整回合，保留所有用户消息及最近回合；这不是语义摘要。
- 项目根目录 `AGENTS.md` 提供规则；`.codeharness/skills/<name>/SKILL.md` 的正文按需加载。
  Skill 可用 `---` 包裹 `description: 简短说明`，目录名作为调用名称。
- `--plugin examples/line_count.py` 演示可信 Python 工具扩展；注册表也提供 `before` / `after` 回调。

`verified` 仅表示当前工作区最后一次测试通过且文件内容仍一致；失败或无法完成的后续测试会使旧验证失效。它不能替代独立功能验收。
Token 预算在请求前估算、返回后按 usage 校正；仅对可能已产生输出的失败尝试（如 5xx、超时、长度截断）按估计输入及输出上限保守预留并标记 estimated，429 限流或鉴权拒绝等明确未生成输出的失败不虚扣输出预算，但仍占用共享请求上限。不是供应商侧的硬计费限额。
每次模型尝试及测试执行使用任务剩余时间，且分别最多 60 秒；Git 查询最多 15 秒。超时在调用边界检查，不能保证立即终止所有宿主进程。
测试在本机执行；路径检查、权限和 Git worktree 不构成操作系统沙箱。
扩展是可信本地 Python 代码，拥有宿主权限；只读子任务不加载自定义扩展。
当前不提供任意 Shell、并行写入或第三方插件兼容性。

模型适配器实现 `complete(messages, tools, max_tokens, *, timeout=None) -> Reply`；`timeout` 为调用剩余时间上限。Chat Completions 适配器在对端返回字符串型 `reasoning_content` 时保留该字段供后续调用，具体供应商兼容性需真实联调。会话 trace 可能包含私有代码、需求或模型返回内容，勿公开整个数据库。

## 独立评测

运行 12 个基础多文件样例（`full`）或 3 个 11 文件多模块后端样例（`multi`），验证初始缺陷与参考修复：

```powershell
python -m codeharness.benchmark --mode fixtures --suite full
python -m codeharness.benchmark --mode fixtures --suite multi
```

首批 5 个（`core`）覆盖购物车折扣、分页、库存、配置合并及 Decimal 发票；`full` 在此基础上增加日期报表、CSV 导入、订单去重、退避计算、商品搜索、运费及指标统计；`multi` 提供 3 个 11 文件多模块后端样例（订单结算管线、多租户 RBAC 网关、财务幂等对账），均需跨 3 个模块联动修复。它们是可复现的业务夹具，不是从真实开源项目采集的 issue。

评测程序在每个全新工作区运行相同的独立验收；验收脚本不在该工作区内。初始版本必须因需求断言失败，然后由参考实现或真实 Agent 独立验证。报告包含运行状态、独立 success、请求次数、Token、耗时和预算跳过项，保存为 `.codeharness/benchmarks/<id>/report.json`。数据库与样例工作区留在报告目录供追溯。

### 真实模型与消融实验

在已配置 `.env`、明确接受本机执行测试代码且已确认调用预算的环境中：

首轮建议固定模型并仅试跑 `discount`，确认原生工具调用、独立验收及预算行为，再扩大到 5 个核心任务。当前联调首选 `glm-5.3`：

```powershell
python -m codeharness.benchmark --mode model --task discount --model glm-5.3 --env-file .env --allow-exec --total-requests 12 --total-tokens 24000
```

`.env` 使用获授权的模型配置，支持 `CODEHARNESS_BASE_URL`、`CODEHARNESS_API_KEY` 和可选 `CODEHARNESS_MODEL`。未设置命令行地址、CodeHarness 或 OpenAI 地址时，也可读取 `DASHSCOPE_BASE_URL` 和 `DASHSCOPE_API_KEY`，并用 `--model` 指定模型。凭据留在本地配置。`--task` 与 `--suite` 互斥。报告的 `diagnostics` 提供模型错误、重试、工具错误及失败验证次数，并按工具名汇总工具错误。

```powershell
python -m codeharness.benchmark --mode model --suite core --env-file .env --allow-exec --total-requests 60 --total-tokens 120000
```

对比委派启用与禁用，在每个任务上使用独立工作区、相同模型、相同单任务限额（默认 12 个请求、24000 Token、180 秒）：

```powershell
python -m codeharness.benchmark --mode model --suite core --variants both --env-file .env --allow-exec --total-requests 120 --total-tokens 240000
```

总预算不足以启动一组对比任务时记为 skipped。供应商实际计费用量可能超过运行时的估算预算。认证或访问被明确拒绝时停止后续任务。只对完整的成对结果比较成功率、Token 和耗时，并考虑模型输出非确定性。`--output-tokens` 调整单次输出上限，默认为 2048。`--output` 可指定尚不存在的报告目录，`--suite full` 扩展到 12 个基础任务，`--suite multi` 运行 3 个 11 文件多模块后端任务。报告 `diagnostics` 同时统计 `delegate_calls` 与 `compactions`。

模型接口支持时，可在 `run`、`resume` 或 `benchmark` 中用 `--reasoning-effort low` 调低推理强度。评测报告会记录显式设置的值。`glm-5.3` 的可选值见 [百炼 GLM 文档](https://help.aliyun.com/zh/model-studio/glm)。

基准验收仍在本机执行模型编写的 Python 代码，独立验收目录不是防篡改安全沙箱。仅用于可信评测任务。

### 模型额度池

将 `models.example.json` 复制到 `.codeharness/models.json`。用供应商控制台更新 `quota_as_of`、`quota_tokens` 和到期日，然后执行 `python -m codeharness.model_pool status` 核对余额。多个工作树使用同一份配置和台账时，传入同一个绝对配置路径。

```powershell
python -m codeharness.benchmark --mode model --task discount --model-pool .codeharness/models.json --models deepseek-v4.1-flash,deepseek-v4.1-flash-1017 --env-file .env --allow-exec --total-requests 12 --total-tokens 24000
```

评测在同一模型内完成整组对照。额度耗尽时会记录已用量，并在另一可用模型上重新运行整组。`run` 和 `resume` 也接受 `--model-pool` 与 `--models`，会话预算按每次实际请求统计。`sessions` 显示会话开始时的模型，每次请求使用的模型可在 `trace` 的 `model_request` 中查看。

### 当前实测与边界

| 评测项 | 结果 | 关键统计与说明 |
| --- | --- | --- |
| 单元测试与契约回归 | 77/78 通过（1 跳过） | 含 16 项本地 HTTP/CLI 契约测试与 4 阶段进程崩溃注入；符号链接测试因本机权限跳过 |
| 参考夹具独立验收 | 15/15 通过 | `full` 12 题 + `multi` 3 题初始断言均失败、参考修复均通过独立验收（0 次模型调用） |
| `glm-5.3`（`core`，`low`，4096） | 4/5（原题面）；`invoice` 澄清后复测 1/1 | 33 次请求、65,570 Token、65.82 秒、0 模型错误；原题面独立验收暴露负数舍入边界差异 |
| `glm-5.3`（`multi`，`low`，4096） | 3/3 全部通过 | 3 个 11 文件后端任务均精准跨 3 模块修复；22 次请求、62,579 Token、53.41 秒、0 模型错误、`write_file` 误用错误由 3 次降至 0 次 |
| 委派子任务边界观察 | `delegate_calls = 0` | 上述样例上下文未超阈值，模型直接并行读取效率更高；实际委派收益仍需在更大仓库上另行验证 |

确定性 demo（启用委派 8 次调用、禁用 5 次调用）均修复折扣并通过测试，仅用于验证执行链路而非模型能力。完整分段记录与复现命令见 [交接记录](HANDOFF.md#最新交接单)。

正常环境使用 `python -m unittest discover -s tests -v` 完整回归。如果明确禁止本地回环连接，可以在 PowerShell 设置 `$env:CODEHARNESS_SKIP_LOOPBACK='1'`，显式跳过 5 项真实本地 HTTP 集成测试；模拟传输与 CLI 工具链测试仍然运行。该模式不等同于完整网络回归。

`python -B scripts/regress.py --tag <标签>` 一次运行单元测试、`full` 与 `multi` 参考夹具及启用、禁用委派的离线 demo，结果与日志写入 `.codeharness/regress/`；`--compare <summary.json>` 与之前的结果对比，`--skip-loopback` 等同于上面的环境变量。CI 在 Ubuntu 与 Windows、Python 3.11～3.13 上运行同一脚本，不调用真实模型。

## 设计取舍

- 执行循环不绑定特定供应商 SDK，明确隔离模型接口、工具权限、上下文、事件持久化和 CLI。
- SQLite 事件保留可复现的输入与执行证据；文件检查点用于判断变化，不是自动事务回滚。
- 优先只读探索、必要时编辑并测试，以独立验收评价任务结果；语法诊断不是功能验证，也不阻断多步中间编辑。
- 轻量且可观测优先于高并发、多模型编排或图形界面；真实模型数据应当驱动下一阶段优化。

设计参考：[Pi](https://github.com/earendil-works/pi)、
[Claude Code 公开文档](https://code.claude.com/docs/en/how-claude-code-works)、
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness)、
[oh-my-pi](https://github.com/can1357/oh-my-pi)。本项目用 Python 独立实现，未复制其运行时代码。

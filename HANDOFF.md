# CodeHarness 交接记录（HANDOFF）

接手本仓库开发前，请按 [AGENTS.md](AGENTS.md) 核对 `git status --short --branch` 与 `git rev-parse HEAD`，以实际源码和实测为准。

## 当前 1 周迭代总览（面向偏后端 Agent 开发求职打磨）

| 阶段 | 目标 | 状态 |
| --- | --- | --- |
| Day 1～2 | P0/P1 核心运行时、工具、上下文、恢复与 CLI 稳定性修复 | 已实现，5 项本地 HTTP 回归已补验，尚未提交 |
| Day 3 | 真实模型联调并建立首批 5 个任务的独立验收基线 | 已完成 glm-5.3 单任务联调及 5 项核心基线 |
| Day 4 | 模型传输容错、统一预算、工具及语法诊断 | 已支持 DashScope 配置，真实评测驱动调整输出上限和工具可用条件 |
| Day 5～6 | 扩充至 12 个多文件业务任务，独立验收、消融对比及崩溃故障注入测试 | 12/12 参考验收通过，5 个核心任务的配对实测已完成，实际委派收益仍待测 |
| Day 7 | 全量回归、更新 `README.md` 评测与架构边界、面试复盘收口 | 本轮完成全量初跑及定向复测，符号链接测试因权限跳过，尚未发布 |

## 最新交接单

### 2026-11-21 晚间评审修复与 `multi` 多模块真实评测收口

基线：`47c5c8da9e68227ed63e22cd098746fcb4d83096`（分支 `main`）；工作区：`D:/Code/python/CodeHarness`；状态：全部开发与实测验证完成，按模块拆分 4 个提交发布到 `origin/main`。

本轮实际修复：
- 安全与配置：恢复缺失的 `.env.example`；移除交接文档中的外部私有路径；修复 `cli.load_env` 对带引号值后 `#` 行内注释误吞后续行的问题。
- 模型与预算：`models.py` 清洗 `tool_calls` 私有字段、对 HTTP 错误仅提取安全 ASCII `error.code`/`error.type` 标识（绝不回显凭据）；`runtime.py` 区分未生成输出的失败（429/401/403/未建连失败不虚扣满额 `output_tokens`，仍计入共享请求上限）。
- 工具体验：`tools.py` `write_file` 捕获 `FileExistsError` 转为友好 `ToolError`（不暴露宿主机绝对路径并引导改用 `edit_file`），`edit_file`/`write_file` 对 `.py` 文件附带非阻塞 `syntax_valid`/`syntax_error` 反馈，`search` 补齐 `src/**/*.py` 零层匹配。
- 多模块评测：`benchmark_tasks.py` 新增 `MULTI_TASKS`（`order-pipeline`、`rbac-gateway`、`ledger-reconcile`，每题 11 个文件跨 3 模块联动修复）；`benchmark.py` 支持 `--suite multi` 并在 `diagnostics`/`summary` 汇总 `delegate_calls` 和 `compactions`。

本轮实测证据：
- 单元测试（含 16 项真实本地 HTTP/CLI 契约测试与 4 阶段进程崩溃恢复测试）：78 项中 77 passed，1 skipped（`test_symlink_cannot_escape_workspace` 本机权限跳过）。
- `glm-5.3` 多模块评测（`--suite multi --model glm-5.3 --env-file .env --reasoning-effort low --output-tokens 4096`）：**3/3 独立验收通过**（均精准修改对应 3 个业务模块），22 次请求、62,579 Token（59,686 输入 / 2,893 输出）、53.41 秒、0 次模型错误、2 次 `edit_file` 错误（自动重试修正）、**`write_file` 误用错误归零**、`delegate_calls=0`、`compactions=0`；报告见 [report.json](.codeharness/benchmarks/glm53-multi-low-20261121/report.json)。

### 2026-11-21 glm-5.3 早期实测（`core` 套件）

基线为 `main` 的 `47c5c8da9e68227ed63e22cd098746fcb4d83096`，工作区为 `D:/Code/python/CodeHarness`。本轮改动与此前 Day 1～7 改动一并保留在工作区，未提交或推送。

| 阶段 | 独立验收 | 模型用量 | 证据 |
| --- | --- | --- | --- |
| `discount` 单任务 | 1/1，Agent 自测通过 | 6 次，12,830 Token，10.33 秒 | [报告](.codeharness/benchmarks/glm53-discount-20261121/report.json) |
| 核心基线，单次上限 2,048 | 3/5，`discount`、`pagination`、`inventory` 通过 | 27 次，72,509 Token（含失败估算），177.47 秒 | [报告](.codeharness/benchmarks/glm53-core-20261121/report.json) |
| 默认推理强度配对，单次上限 4,096 | 开启委派 3/5，关闭委派 4/5 | 开启组 23 次、64,938 Token、227.20 秒。关闭组 27 次、70,151 Token、140.11 秒。两组均含失败估算 | [报告](.codeharness/benchmarks/glm53-core-paired-20261121/report.json) |
| `low` 定向联调 | `config` 和 `invoice` 通过，自测也通过 | 合计 12 次，23,571 Token，20.89 秒 | [报告](.codeharness/benchmarks/glm53-low-reasoning-20261121/report.json) |
| `low` 正式 CLI 核心评测，原题面 | 4/5，`invoice` 独立验收失败 | 33 次，65,570 Token，65.82 秒，0 次模型错误 | [报告](.codeharness/benchmarks/glm53-core-low-20261121/report.json) |
| `low` 发票题面澄清后复测 | `invoice` 1/1，自测也通过 | 8 次，17,722 Token，13.29 秒 | [报告](.codeharness/benchmarks/glm53-invoice-contract-20261121/report.json) |
| `low` 多模块后端评测（`multi` 3 题） | 3/3 全部通过，自测均通过 | 22 次，62,579 Token，53.41 秒，0 次模型错误 | [报告](.codeharness/benchmarks/glm53-multi-low-20261121/report.json) |

首轮基线的 `config` 和 `invoice` 都遇到输出截断，Agent 拒绝执行不完整的工具调用。`pagination` 和 `inventory` 已通过自测和独立验收，最终状态均为 `budget_exhausted`。基线有 4 次 Git 工具错误，配对实测降为 0 次。配对完成了 5 组任务，实际启动的委派子任务为 0，组间差异只能说明这批任务在两种开关设置下的单次表现。

`low` 正式评测的发票任务通过了 Agent 自测，独立验收发现 `money.cents` 仍按 `ROUND_DOWN` 处理负数。题面已明确 `invoice.total` 和 `money.cents` 均须按 `ROUND_HALF_UP` 舍入，并保留全部验收断言。4/5 核心结果与更新题面后的 1/1 单项结果分别记录。

CLI 和评测现在支持读取带引号的多行 `.env` 值及行内 `#` 注释，在未提供其他模型接口地址时成对读取 `DASHSCOPE_BASE_URL` 和 `DASHSCOPE_API_KEY`。通过 `--model` 固定 `glm-5.3`，`MODEL` 列表不参与自动切换。Git 工具只在仓库根提供。评测支持 `--output-tokens`，默认 2048。CLI 和评测可显式传入 `--reasoning-effort`，不传时使用供应商默认值。评测报告记录显式设置的推理强度。[百炼 GLM 文档](https://help.aliyun.com/zh/model-studio/glm)

### 复现真实评测

从项目根执行以下命令，使用项目本地 `.env`（凭据仅留本地，不入库）。命令用当前题面生成新的 `.codeharness/benchmarks/<id>/report.json`。

```powershell
# 5 个基础核心任务
python -B -m codeharness.benchmark --mode model --suite core --model glm-5.3 --env-file .env --allow-exec --reasoning-effort low --output-tokens 4096 --total-requests 60 --total-tokens 120000

# 3 个 11 文件多模块后端任务
python -B -m codeharness.benchmark --mode model --suite multi --model glm-5.3 --env-file .env --allow-exec --reasoning-effort low --output-tokens 4096 --max-requests 18 --max-tokens 40000 --total-requests 54 --total-tokens 120000
```

核对每个任务的 `success`、`agent_status`、`agent_verification`、`usage` 和 `diagnostics`（含 `delegate_calls` 与 `compactions`）。`success` 来自独立验收。报告和会话数据库留在本地。后续如需验证真实委派收益，可在更大上下文的多模块仓库上运行 `--variants both` 配对实验。


## Day 3～7 交接记录（历史）

```text
任务：Day 3～7 模型传输、预算、工具、独立评测与恢复测试；负责人：Codex
基线：47c5c8da9e68227ed63e22cd098746fcb4d83096；工作区：D:\Code\python\CodeHarness；分支：main
范围：Day 1～2 未提交差异继续保留；models.py、runtime.py、tools.py、demo.py、cli.py、benchmark.py、benchmark_tasks.py、tests/test_runtime.py、tests/test_transport_cli.py、tests/test_benchmark.py、tests/test_recovery.py、README.md、HANDOFF.md
公共接口：Model.complete 新增关键字 timeout；Limits 新增 model_attempts；Agent 新增 enable_delegate；CLI 新增 --model-attempts 和 --no-delegate；model_request 增加剩余时间，新增 model_error/model_retry 事件，失败用量标记 estimated/failed_attempt。
交付：未提交工作区差异；状态：开发实现与离线验收已完成，真实模型评测与发布受阻。
验证：
- 使用短临时目录，设置 CODEHARNESS_SKIP_LOOPBACK=1 后运行 `python -m unittest discover -s tests -v` -> 66 项，60 passed，6 skipped，无失败。5 项真实本地 HTTP 测试明确跳过，1 项符号链接创建缺权限。
- `python -m codeharness.benchmark --mode fixtures --suite full --output .codeharness/benchmarks/day3-7-fixtures-ecfe5541` -> 12/12 初始需求断言失败、12/12 参考实现独立验收通过，0 次真实模型调用。报告位于该目录的 report.json，模式 reference_fixture_validation，不是模型成功率。
- 确定性 demo 启用委派 8 次请求、禁用委派 5 次请求，均 verified；不代表真实消融收益。
- 进程级 os._exit 故障注入：工具未开始、已开始、已写入、已记录结果四种阶段恢复通过，未重放未知写操作；独立验收与 Agent 验证分离的测试通过。
- 模拟 HTTP 请求/回复、有限重试、Retry-After、剩余时间、请求/Token 预算、权限拒绝终止以及完整 CLI 工具链通过回归。
未验证或阻塞：当前无真实模型名、地址和密钥配置；本地回环连接受环境权限限制（此前确认 WinError 10013）；真实模型评测和供应商兼容性、真实消融结果尚未测量；Git 元数据目录只读，未提交或推送。
下一步：按 README 在可访问模型的授权环境先运行 core 5 个任务，明确总请求和 Token 预算；再决定是否运行配对消融及 full。开放本地回环测试后全量回归，并在 Git 可写环境提交、推送。
```

## Day 3～7 实现清单

- 模型传输：429/常见临时 5xx、可重试连接错误的有限重试；Retry-After 或指数退避；所有实际尝试占用共享预算，未知用量保守预留；权限/认证拒绝终止任务与评测。保留 `reasoning_content` 以支持需要该字段的供应商，未宣称已完成真实兼容验证。
- 工具：`git_status`、`git_diff`（只读且过滤受保护路径）、glob 搜索、单文件 unittest、非阻塞式 `check_syntax`；失败的后续测试不沿用旧通过结果；模型和测试使用任务剩余时间。
- 评测：`codeharness.benchmark` 提供 core/full、参考夹具检查和需显式授权的真实模型模式；新的工作区和会话库、独立验收脚本、固定单任务预算和总预算、委派开关及 JSON 报告。12 个样例为可复现的业务小仓库，而非实际开源 issue 数据集。
- 文档：README 增加使用命令、指标边界、评测口径、设计取舍及当前实测；无新增运行时依赖。

## Day 1～2 交接记录（历史）

```text
任务：Day 1～2 P0/P1 核心运行时稳定性与边界修复、收尾验收；负责人：Codex（接手 Antigravity 的改动）
基线：47c5c8da9e68227ed63e22cd098746fcb4d83096；工作区：D:\Code\python\CodeHarness；分支：main
范围：codeharness/tools.py、codeharness/context.py、codeharness/store.py、codeharness/runtime.py、codeharness/cli.py、tests/test_runtime.py、tests/test_transport_cli.py、AGENTS.md、HANDOFF.md（公共接口变化：tool_reconciled 新增 started 字段；load_skill 返回值精简为 loaded/chars，正文仍在 skill_loaded 事件与 messages[0]；cli.load_env 改为返回 dict 不修改 os.environ）
交付：未提交工作区差异；状态：实现收尾，完整回归与发布受阻
验证：
- 运行时：`python -m unittest discover -s tests -p test_runtime.py -v` -> 34 项，33 passed，1 skipped（本机未授权创建符号链接）。
- 非网络 CLI：`python -m unittest discover -s tests -p test_transport_cli.py -k test_git_isolation -k test_cli_isolate -k test_load_env -k test_missing_model_configuration -v` -> 4/4 passed；使用短临时目录避免 Windows Git worktree 路径长度限制。
- 全量初次回归：`python -m unittest discover -s tests -v` -> 42 项中 5 failures、1 error、1 skipped；其中 Git worktree 路径长度问题已通过上述复测，另 5 项 HTTP 测试受本地回环连接权限限制（独立 socket 检查返回 WinError 10013），未计为通过。
- 离线确定性演示（独立临时目录及会话库）：`python -m codeharness demo --directory <tmp>/demo --store <tmp>/state.sqlite3 --json` -> exit 0，status=verified，verification=passed，changed_files=["basket.py"]，8 次请求（确定性适配器，不代表真实模型成功率）。
未验证或阻塞：
- test_symlink_cannot_escape_workspace 因本机未授权创建符号链接跳过
- 当前环境不允许本地回环连接，尚未重新验证 5 项模拟 HTTP 测试；此前 Antigravity 交接报告其 9 项传输/CLI 测试均通过
- 当前环境 Git 元数据目录只读，网络受限，未执行 git commit 或 git push
- 尚未进行真实外部 LLM 模型接口联调（计划在 Day 3～6 完成）
下一步：在允许回环连接且 Git 仓库可写的环境完成全量回归，确认通过后提交并推送；随后按新版计划启动 Day 3 的真实模型基线评测。
```

## 本轮实际修复清单（供接棒核对）

1. `codeharness/tools.py`
   - `Workspace.files()` 补齐对 `names` 的 `HIDDEN` 过滤，修复 Git worktree 下 `.git` 文件触发 `ToolError` 导致 `--isolate` 运行即崩溃的隐蔽缺陷。
   - `Workspace.snapshot(use_cache=True)` 增加 `(mtime_ns, size)` 内存哈希缓存，`edit_file`/`write_file` 写后即时刷新缓存。
   - `edit_file` 兼容 Windows CRLF 与 UTF-8 BOM 多行替换并保持原换行与 BOM；`read_file` 增加不存在与目录校验。
   - `Registry.invoke` 补全 `boolean`/`number`/`array`/`object` JSON Schema 校验（排除 `bool` 混入 `integer`/`number`）。
2. `codeharness/context.py`
   - `SKILL.md` 与 `AGENTS.md` 统一按 `utf-8-sig` 读取，`AGENTS.md` 超 10000 字符附截断提示。
   - `Context.prepare` 将压缩摘要合并入首条 `system`（不再插入第二条 `system`），消除 ≤ 2 轮假 `context_compacted`，并对保留区内非末条超长 `tool` 消息做保留 `artifact_id` 的二次裁剪。
3. `codeharness/store.py`
   - `repair_pending` 结合 `tool_started` 区分“执行中断（副作用不确定）”与“前序中断导致尚未执行”。
4. `codeharness/runtime.py`
   - 仅在 `write`/`execute` 工具后写 `checkpoint`（`run_tests` 复用单次 `use_cache=False` 快照同时写入 `verification` 与 `checkpoint`）。
   - 任务启动（包括恢复）及结束时重新核对实际文件内容，不依赖哈希缓存，避免仅凭文件大小与修改时间误判验证结果。
   - `load_skill` 工具返回值仅返回确认信息，消除正文在 `system` 与 `tool` 消息中的双份占用。
   - 恢复无 `checkpoint` 时兜底使用 `baseline`；工具循环内超时统一落入 `status="timeout"`；残余预算低于 `min(256, output_tokens)` 直接判 `budget_exhausted`；兜底工具与插件未知异常防止会话卡死 `running`。
5. `codeharness/cli.py`
   - 延后 `run`/`demo` 打开 `Store` 的时机，并在 `isolated_workspace` 检查干净状态时放行纯未跟踪的 `?? .codeharness/`，修复普通无 `.gitignore` Git 仓库 `--isolate` 自污染及报错残留。
   - `load_env` 改为返回 `dict` 并以 `os.environ` 优先合并，避免 `.env` 敏感键透传给测试子进程。
6. `tests/test_runtime.py`、`tests/test_transport_cli.py`
   - 修复 `test_duplicate_tool_ids_rejected` 假阳性断言，并补齐上述所有修复点的单元测试与 CLI `--isolate` 集成测试。
   - 增加对验证快照与实际文件内容不一致的回归测试；补充模型回调相关任务的结果断言，避免运行时异常兜底掩盖测试断言失败。

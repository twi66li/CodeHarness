# CodeHarness 改进计划（IMPROVEMENT_PLAN）

本文件给出下一轮迭代的有序执行步骤。按 S0 → S14 依次推进，每步完成并通过验收后再开始下一步。
执行规则遵循 [AGENTS.md](AGENTS.md)；阶段交接仍写入 [HANDOFF.md](HANDOFF.md)，本文件只维护计划与进度。

**执行方式**：由 Codex 一人按 HANDOFF.md 执行总清单的顺序串行完成（S0 → S0b → M0 → S1～S14），暂不使用多 Agent 并行。执行总清单、日期检查点、模型额度与使用规则、分支与合并约定、Codex 任务书和执行记录，见 [HANDOFF.md 的“2026-11-22 改进计划启动”一节](HANDOFF.md#2026-11-22-改进计划启动执行总清单codex-单人串行)。下表的“依赖”是逻辑依赖。

## 目标

1. **补证据**：让上下文压缩与只读委派在真实模型评测中被实际触发，并用多次运行的统计结果说话。
2. **去隐患**：修复输出截断即失败、事件存储平方级开销、全量文件遍历等在大仓库上会暴露的问题。
3. **强能力**：补齐多处编辑、只读并行与死循环检测，降低请求次数。
4. **好展示**：架构图、CI、英文文档与可复现的实验表格。

## 进度总览

| 步骤 | 阶段 | 内容 | 依赖 | 预估 | 状态 |
| --- | --- | --- | --- | --- | --- |
| S0 | 0 基线 | 冻结基线、全量离线回归 | — | 0.25d | ◐ 本地回归通过，待 CI |
| S0b | 0 基线 | 改进前真实模型基线（deepseek-v4.1-flash，S0 提交） | S0 | 0.25d | ☐ |
| M0 | 0 基线 | 模型池：额度台账与用完自动切换 | S0 | 1d | ☐ |
| S1 | 1 稳定性 | 拆分 `Agent.run`（纯重构） | S0 | 0.5d | ☐ |
| S2 | 1 稳定性 | 输出截断可恢复 | S1 | 0.5d | ☐ |
| S3 | 1 稳定性 | 死循环检测与 `stalled` 状态 | S1 | 0.5d | ☐ |
| S4 | 1 稳定性 | 测试子进程环境白名单与敏感文件保护 | S0 | 0.25d | ☐ |
| S5 | 2 上下文 | 稳定 system 前缀、Skill 注入方式、记录 `cached_tokens` | S1 | 0.75d | ☐ |
| S6 | 2 上下文 | Token 估算统一与校准 | S5 | 0.5d | ☐ |
| S7 | 3 规模 | 运行时内存态、存储去重与检查点差量 | S1, S6 | 1.5d | ☐ |
| S8 | 3 规模 | 文件遍历遵循 `.gitignore`、搜索支持正则 | S0 | 0.5d | ☐ |
| S9 | 4 工具 | `apply_patch` 与 `--disable-tool` | S1 | 1d | ☐ |
| S10 | 4 工具 | 同批只读工具并行执行 | S7 | 0.5d | ☐ |
| S11 | 5 评测 | `--repeats` 与统计汇总 | S0 | 0.5d | ☐ |
| S12 | 5 评测 | 大仓库评测套件 `large`（及可选 `external`） | S8 | 1.5d | ☐ |
| S13 | 5 评测 | 真实模型实验矩阵（按现有额度重排，约 1.4M Token） | S2–S12、M0、S0b | 1d | ☐ |
| S14 | 6 展示 | 架构图、时间线、CI、英文 README、简历口径 | S13 | 1d | ◐ 架构图、CI、英文 README 已完成；时间线、实测表、简历口径待做 |

合计约 12 个工作日。真实模型调用只出现在 S0b、M0 实测和 S13（以及可选的 G1），由 Codex 按规则执行，额度分配见 HANDOFF.md 的“模型额度与使用规则”；其余步骤均用离线测试验收。

### 排序理由

- **S1 先重构**：S2、S3、S7、S10 都要修改执行循环。先把约 200 行的 `run` 拆开，后续每步的改动面和冲突都更小；现有 82 项测试足以兜住纯重构。
- **S2～S4 先做**：改动小、收益直接，其中 S2 直接对应首轮基线 `config`、`invoice` 的失败原因。
- **S5、S6 在 S7 之前**：存储改造要记录新的 usage 字段（`cached_tokens`、估算输入），先定字段再改存储，避免事件格式改两次。
- **S7、S8 在 S12 之前**：大仓库评测会直接放大事件存储与遍历开销。
- **M0 尽早做**：真实调用必须在额度耗尽时自动换模型，而不是整体停止；M0 只改评测层和模型包装，不影响 S0b 测得的“改进前运行时”。
- **S0b 尽早跑**：S13 改用 deepseek 模型，改进前对照必须同模型；deepseek-v4.1-flash 于 12/13 到期。
- **S13 最后统一跑**：所有改动完成后一次性跑实验矩阵，节省额度并保证口径一致。

---

## 通用执行规则

每一步都按以下流程执行：

1. 从最新 `main` 建立分支 `codex/sN-<slug>`，记录 `git rev-parse HEAD` 作为该步基线。
2. 先写或更新失败的测试，再实现；只修改本步列出的文件，必要的调用方同步修改。
3. 运行本步列出的最小测试；每个阶段结束时运行一次全量离线回归（单元测试、`full`/`multi` 参考夹具、启用与禁用委派的 demo），并与 S0 对比：
   ```powershell
   python -B scripts/regress.py --tag sN --compare .codeharness/regress/<s0 目录>/summary.json
   ```
   结果写入 `.codeharness/regress/<tag>-<时间>/`（已被 `.gitignore` 忽略），含各项日志与 `summary.json`。
   本地回环受限时加 `--skip-loopback`；Windows 默认把测试临时目录设为 `<系统盘>\cht`，规避 worktree 路径长度限制。
4. 保持文件原有换行：`codeharness/` 下的 Python 源码为 CRLF，Markdown 为 LF。`git diff --check` 后一步一个提交，提交信息使用 `feat(...)/fix(...)/refactor(...)/test(...)/docs(...)` 前缀。
5. **事件格式兼容**：任何新增或修改的事件字段，都必须保证旧会话库仍能 `sessions`、`trace`、`resume`。涉及事件格式的步骤需附一条"用旧格式事件构造会话并恢复"的测试。
6. 阶段结束时在 HANDOFF.md 写一条交接单，并回到本文件更新进度表状态。

---

## 阶段 0：基线

### S0 冻结基线

**目标**：确定改进前的可比较基线。

**已确认事实**（2026-11-22，读取 `.git` 与已有报告）
- 基线提交：`7263bb2ed9c8469e54fbf6acef812d7cde5d3bff`，分支 `main`，与 `origin/main` 一致；另有已合并的历史分支 `codex/python-runtime-v1`，无额外 worktree。
- HANDOFF.md 中写的基线 `47c5c8da…` 是 4 个模块提交之前的旧基线，本轮以 `7263bb2` 为准。
- 新增未跟踪文件：`IMPROVEMENT_PLAN.md`、`scripts/regress.py`（随 S0 一起提交）。
- 已有真实模型基线（glm-5.3，每题 1 次，作为改进前对照）：

  | 报告 | 配置 | 独立验收 | 请求 | Token（入/出） | 耗时 |
  | --- | --- | --- | --- | --- | --- |
  | `glm53-core-low-20261121` | core，`low`，4096 | 4/5 | 33 | 63,248 / 2,322 | 65.8s |
  | `glm53-multi-low-20261121` | multi，`low`，4096 | 3/3 | 22 | 59,686 / 2,893 | 53.4s |
  | `glm53-core-paired-20261121` | core，默认推理，4096 | 委派开 3/5 · 关 4/5 | 23 / 27 | 50,747 / 14,191 · 59,369 / 10,782 | 227.2s / 140.1s |

**动作**
1. 在项目根执行离线回归（不调用真实模型，约 1～3 分钟）：
   ```powershell
   python -B scripts/regress.py --tag s0
   ```
   预期：单元测试 78 项、OK（skipped=1，符号链接）；夹具 `full` 12/12、`multi` 3/3；demo 启用委派 8 次请求、禁用 5 次，均为 `verified`。
2. 记下输出目录 `.codeharness/regress/s0-<时间>/`，后续各阶段用 `--compare` 指向其中的 `summary.json`。
3. 提交计划和脚本：
   ```powershell
   git add IMPROVEMENT_PLAN.md scripts/regress.py
   git commit -m "docs: 新增改进计划与离线回归脚本"
   ```
4. 改进前的真实模型基线改为单独的 S0b（见下文），可选的 glm-5.3 重复基线见 HANDOFF.md 的“G1”。

**验收**：离线回归结果与预期一致，基线数据写入 HANDOFF.md，进度表 S0 标记完成。
若有失败或与预期不符，先排查原因并记录，不进入 S1。

---

### S0b 改进前真实模型基线

**目标**：S13 改用 deepseek 模型（glm-5.3 额度 11/23 到期），改进前后的对比必须同模型，所以先在 S0 提交上用 deepseek-v4.1-flash 测一遍。

**动作**：在检出 S0 提交的临时 worktree 中，先跑 `discount` 冒烟，再把 `core`、`multi` 各跑 2 轮，输出到主仓库的 `.codeharness/benchmarks/pre-ds-*`。命令、停止条件和用量上限见 HANDOFF.md 的“S0b”。

**验收**：
- 冒烟通过，2 轮 8 题的报告完整。
- 用量与推理强度设置写入执行记录。
- 若中途遇到额度耗尽，记录 HTTP 状态码和错误码，供 M0 使用。

### M0 模型池：额度台账与用完自动切换

**问题**
- 可用模型的免费额度与到期日各不相同，都开启了“用完即停”。耗尽后接口返回 HTTP 403。
- `models.py` 把所有 401/403 当作 `access_denied`，评测会整体停止，不会换下一个模型。
- 跨模型混跑会污染对比实验，所以切换必须有边界并且记录在案。

**设计原则**：`ModelPool` 实现现有的 `Model` 协议，像包装器一样替换单个 `ChatModel`。`runtime.py` 不做任何修改。

**改动**
- `codeharness/models.py`（仅此一处）：`ModelError` 新增 `status: int | None`、`code: str | None`（`safe_error_tag` 提取出的 ASCII 错误码，不带括号）、`quota_exhausted: bool = False`；`ChatModel` 在 HTTP 错误时赋值。错误消息文本保持不变。
- 新建 `codeharness/model_pool.py`：
  - **配置**：读取 JSON，只用标准库。仓库提交 `models.example.json`，本地使用被 `.gitignore` 忽略的 `.codeharness/models.json`。示例：
    ```json
    {
      "quota_as_of": "2026-11-22T23:00:00+08:00",
      "timezone_offset": "+08:00",
      "base_url_env": "DASHSCOPE_BASE_URL",
      "api_key_env": "DASHSCOPE_API_KEY",
      "ledger": "D:/Code/python/CodeHarness/.codeharness/quota-ledger.jsonl",
      "safety_margin": 0.1,
      "quota_error_codes": [],
      "models": [
        {"name": "deepseek-v4.1-flash", "quota_tokens": 918740, "expires": "2026-12-13", "reasoning_effort": null},
        {"name": "deepseek-v4.1-flash-1017", "quota_tokens": 996950, "expires": "2027-01-17", "reasoning_effort": null},
        {"name": "qwen3.8-max-0902", "quota_tokens": 145940, "expires": "2026-12-01", "reasoning_effort": null},
        {"name": "glm-5.3", "quota_tokens": 294940, "expires": "2026-11-23", "reasoning_effort": "low"},
        {"name": "qwen3.8-flash", "quota_tokens": 41780, "expires": "2026-11-25", "reasoning_effort": null}
      ]
    }
    ```
    可选字段 `cap_tokens` 可以人为压低某个模型的可用额度，有效额度取 `min(quota_tokens, cap_tokens)`。
  - **台账**：使用 JSONL 追加写入，记录 `{time, model, input_tokens, output_tokens, estimated, kind}`，`kind` 取 `usage`、`exhausted` 或 `imported`。剩余额度按 `有效额度 − quota_as_of 之后的累计用量` 计算。用户按控制台数字更新 `quota_tokens` 和 `quota_as_of` 后，之前的台账记录自动不再计入。台账路径对所有 worktree 统一。
  - **可用性**：以下情况视为模型不可用：
    - 到期日当天及之后（按配置的固定偏移计算，不依赖 `zoneinfo`，因为 Windows 默认没有时区数据库）；
    - 已有 `exhausted` 记录；
    - 剩余额度小于本次所需额度 × (1 + `safety_margin`)。
  - **额度耗尽的判断**：
    - 403，且错误码在 `quota_error_codes` 中，或错误码包含 `quota`、`freetier`、`allocation`（不区分大小写）：视为耗尽；
    - 429：只有错误码在 `quota_error_codes` 中才视为耗尽，其他情况仍按限流有限重试；
    - 401 以及其他 403：仍视为访问被拒绝，整体停止。
  - **`ModelPool.complete()`**：
    - 调用前检查当前模型是否还有 “估算输入 + max_tokens” 的余量，不够就主动切换；
    - 调用后把 usage 写入台账；失败的尝试按 `consume_output_budget` 记录估算用量；
    - 判定为耗尽时，写入 `exhausted` 记录。如果 `switch_mid_session=True`，切换到下一个可用模型并重发同一请求；否则抛出 `ModelError(quota_exhausted=True)`。
    - `name` 属性返回当前使用的模型，因此每条 `model_request` 事件都会记下实际使用的模型。
    - 所有模型都不可用时，抛出 `ModelError(quota_exhausted=True)`，消息中列出各模型的剩余额度与到期日。
  - **命令行**：`python -m codeharness.model_pool status [--config]` 列出各模型的有效额度、已用、剩余、到期日和状态；`record --report <report.json> --model <name>` 把旧格式评测报告的用量导入台账；`mark-exhausted <name>` 手动标记耗尽。
- `codeharness/benchmark.py`（`run_suite()`、`main()`）：
  - 新增 `--model-pool FILE` 和 `--models a,b,c`（覆盖配置中的顺序）。不传 `--model-pool` 时，行为与现在完全一致。
  - 以“对比单元”（一个任务的全部 variant）为粒度选择模型：所需额度为单用例 `max_tokens × variant 数`。同一对比单元内不切换模型。
  - 用例中途耗尽时，该行记为 `skipped: model_quota_exhausted` 并保留已用量，然后在下一个可用模型上重跑整个对比单元，工作区为 `<task>/<variant>/<model>`（S11 合入后为 `<task>/<variant>/r<k>-<model>`）。
  - 报告中每行带 `model` 字段，汇总增加 `summary_by_model`。原有的 `total_requests`、`total_tokens` 检查继续生效。每个模型的 `reasoning_effort` 取自配置；命令行显式传入的值优先。
  - 所有模型都不可用时，其余用例记为 `skipped: quota_exhausted`，正常写完报告后退出。
- `codeharness/cli.py`：`run`、`resume` 支持 `--model-pool`、`--models`，并启用 `switch_mid_session=True`。切换时在终端输出一行提示。README 说明 `sessions` 表中的 `model` 列是会话开始时的模型，实际使用的模型以 trace 中的 `model_request` 为准。
- README：在“独立评测”中新增模型池用法，说明“对比只在同一模型内进行”。

**测试**（新建 `tests/test_model_pool.py`，全部离线，使用假模型和可注入的时钟）
- 主动切换：剩余额度不足时，调用前切换到下一个模型。
- 被动切换：403 加额度类错误码时切换；403 加其他错误码时仍判定为访问被拒绝并停止；429 不切换，按重试处理。
- 到期：到期日当天跳过；`cap_tokens` 生效。
- 台账：跨进程（新实例）累计正确；`quota_as_of` 之前的记录不计入；`record` 能导入旧报告。
- 评测：同一对比单元使用同一模型；中途耗尽后在下一个模型上重跑整个对比单元；全部耗尽时报告完整；不传 `--model-pool` 时与原行为一致（现有 `tests/test_benchmark.py` 全部通过）。
- 会话：`run` 中途切换后，`model_request` 事件记录了两个模型，最终状态正常。

**验收**
- 上述测试全部通过，`scripts/regress.py` 与 S0 一致。
- 可选的真实验证见 HANDOFF.md 的“M0 实测”。

---

## 阶段 1：稳定性与安全

### S1 拆分 `Agent.run`（纯重构）

**问题**：`runtime.py` 的 `Agent.run` 同时负责会话创建与恢复、预算检查、模型调用与重试、工具执行、结果结算，超时判断重复出现 8 处以上，后续改动风险高。

**改动**（`codeharness/runtime.py`）
- 引入循环内部状态 `LoopState`（`sid`、`readonly`、`deadline`、`local_requests`、`failed_attempts`、`status`、`answer`）。
- 拆分为：
  - `_open_session(task, session_id, parent_id, readonly) -> (sid, readonly, baseline)`：新建或恢复、`repair_pending`、恢复检查消息。
  - `_next_request(state, registry, context) -> Reply | None`：预算检查、上下文准备、调用模型、重试与退避。
  - `_execute_calls(state, registry, calls) -> bool`：逐个执行工具、写 `tool_started` / `tool_finished` / `checkpoint` / `verification`，返回是否停止。
  - `_finalize(state, baseline) -> Result`：计算 `changed_files`、`verification`、最终状态。
  - `_timed_out(state, message=...)`：统一超时判断与状态赋值。
- 不修改任何事件名、字段、状态值或对外接口。

**测试**：不修改现有测试断言。`tests/test_runtime.py`、`tests/test_recovery.py`、`tests/test_transport_cli.py` 全部通过。

**验收**
- 全量回归结果与 S0 一致；demo 请求次数仍为 8 / 5；fixtures 15/15。
- `run` 主体不超过 40 行，每个拆出的方法不超过 80 行。

### S2 输出截断可恢复

**问题**：`models.py` 在 `finish_reason == "length"` 时抛出不可重试的 `ModelError`，`runtime.py` 中 `not exc.retryable` 直接 `raise`，被外层捕获为 `status="error"`，整个任务失败。首轮基线 `config`、`invoice` 均因此失败。

**改动**
- `codeharness/models.py`
  - `ModelError` 新增 `truncated: bool = False` 和 `usage: tuple[int, int] | None`。
  - 截断时先解析 `usage`，再抛出 `ModelError(..., truncated=True, usage=..., consume_output_budget=True)`。
- `codeharness/runtime.py`
  - 单独维护 `truncations` 计数，不占用 `model_attempts` 的失败次数。
  - 截断时：按供应商 usage 记账（缺失时按估算保守记账并标记 `estimated`）；写 `model_truncated` 事件 `{"attempt": n, "max_tokens": x}`；追加一条 user 消息：
    > 上一次回复达到单次输出上限被截断，已丢弃。请把修改拆成多次较小的 edit_file 或 apply_patch 调用，每次只改一处，不要在一次回复中输出整文件。
  - 第一次截断后将本轮 `output_tokens` 提升为 `min(2 × limits.output_tokens, 8192, 剩余预算)`，之后恢复默认值。
  - 新增 `Limits.truncation_retries = 2`；超过后以 `status="error"`、`answer="模型输出连续被截断"` 结束。
- `codeharness/benchmark.py`：`diagnostics` 增加 `truncations`。

**说明**：截断的 assistant 消息不入库，因此追加的 user 消息不会破坏 `tool_calls` 与 `tool` 结果的配对。

**测试**（`tests/test_runtime.py`）
- 模拟模型第一次截断、第二次正常完成 → 最终 `verified`；断言第二次请求的 `max_tokens` 被提升、提示消息存在、请求次数计入预算。
- 连续截断超过上限 → `status="error"`，且不重复记账。
- `tests/test_transport_cli.py`：HTTP 层返回 `finish_reason=length` 时异常带 `truncated=True` 和 usage。

**验收**：上述测试通过；全量回归无回退。

### S3 死循环检测与 `stalled` 状态

**问题**：模型反复调用同一工具、得到同一错误时，只能靠请求或 Token 预算兜底，白白消耗预算。

**改动**（`codeharness/runtime.py`、`codeharness/cli.py`、`codeharness/benchmark.py`）
- 从最近的 `tool_finished` 事件计算签名 `sha256(name + 规范化 JSON 参数 + 结果摘要)`。签名包含结果，所以"编辑后重新读取"这类合法重复不会被误判。签名从事件推导，恢复后仍保持一致。
- 规则：
  - 同一签名连续出现 3 次 → 追加一次 user 提示（"你已重复相同操作 3 次且结果相同，请换一种方法或说明阻塞原因"），每个签名只提示一次。
  - 连续 4 次工具错误且错误文本相同（跨工具）→ 同样提示。
  - 同一签名连续出现 5 次 → 以新状态 `stalled` 结束。
- CLI 退出码与 `benchmark.summarize` 增加 `stalled`；README 状态说明同步。

**测试**：模拟模型重复读取同一文件 → 第 3 次后出现提示，第 5 次后 `stalled`；读取—编辑—读取交替 → 不触发；恢复会话后计数延续。

**验收**：测试通过；fixtures 与 demo 不受影响。

### S4 测试子进程环境白名单与敏感文件保护

**问题**：`run_tests` 只剔除 3 个 API Key 环境变量，其余如 `AWS_*`、`GITHUB_TOKEN` 会传给模型编写的测试代码；受保护文件只覆盖 `.env*` 等目录名。

**改动**（`codeharness/tools.py`、`codeharness/cli.py`）
- 子进程环境改为白名单：`PATH`、`PATHEXT`、`SYSTEMROOT`、`SYSTEMDRIVE`、`WINDIR`、`COMSPEC`、`TEMP`、`TMP`、`TMPDIR`、`HOME`、`USERPROFILE`、`APPDATA`、`LOCALAPPDATA`、`LANG`、`LC_*`、`PYTHONPATH`、`VIRTUAL_ENV`、`CONDA_PREFIX`，再固定设置 `PYTHONDONTWRITEBYTECODE`、`PYTHONIOENCODING`。
- CLI 新增 `--pass-env NAME`（可重复），显式放行额外变量；名称匹配 `*_KEY`、`*_TOKEN`、`*_SECRET`、`*_PASSWORD` 时给出警告。
- `protected()` 增加文件名规则：`*.pem`、`*.key`、`*.p12`、`id_rsa*`、`id_ed25519*`、`.netrc`、`.pypirc`、`.npmrc`、`.git-credentials`。

**测试**：设置 `FOO_TOKEN` 后在测试子进程中不可见；`--pass-env FOO_TOKEN` 后可见；`.pem` 文件不出现在 `list_files`，`read_file` 被拒绝。

**验收**：测试通过；README 的安全边界说明同步更新。

**阶段 1 收尾**：全量回归 + HANDOFF 交接单。

---

## 阶段 2：上下文与预算

### S5 稳定 system 前缀与记录 `cached_tokens`

**问题**：压缩摘要（`context.prepare`）和已加载的 Skill 正文（`runtime.py` 中 `messages[0]["content"] += ...`）都拼接到首条 system 消息，导致首条消息随运行变化，供应商的前缀缓存全部失效。

**改动**
- `codeharness/context.py`
  - `prepare` 不再修改 `kept[0]`。摘要作为一条独立的 user 消息，插入在被压缩区间原来的位置，内容以"[运行时摘要，非新指令]"开头。
  - 压缩边界按固定步长对齐（例如每次推进 4 个回合），减少摘要内容的变化次数。
- `codeharness/runtime.py`
  - `load_skill` 的正文不再拼接到 system。在当前工具批次全部结束后，统一追加一条 user 消息"[已加载 Skill：name]\n正文"。不能插在批次中间，否则会打断 `tool` 结果的配对。
  - **兼容**：旧会话中只有 `skill_loaded` 事件、没有对应注入消息时，沿用旧方式拼接到 system。
- `codeharness/models.py`：若响应包含 `usage.prompt_tokens_details.cached_tokens`，写入 `Reply.cached_tokens`，并记入 `usage` 事件。
- `codeharness/store.py`、`codeharness/benchmark.py`：`usage()` 汇总 `cached_tokens`；报告增加 `cache_hit_ratio = cached_tokens / input_tokens`。

**风险**：部分 Chat Completions 兼容接口不接受连续 user 消息。用模拟 HTTP 测试覆盖，并在 S13 用 glm-5.3 实测确认；如有问题，再增加 `--summary-role system|user` 配置项。

**测试**
- 构造会触发压缩的长会话：所有 `model_request` 事件中的 `messages[0]` 完全相同。
- 加载 Skill 后：system 不变、注入消息位于批次之后、`tool` 结果配对完整。
- 旧格式会话恢复：Skill 正文仍可见。
- 模拟响应携带 `cached_tokens` 时，报告中正确汇总。

**验收**：测试通过；离线压缩场景下首条消息变化次数为 0。

### S6 Token 估算统一与校准

**问题**：`runtime.py` 与 `models.py` 各自用 `len(json) // 3 + 1` 估算 Token。系统提示词和工具描述以中文为主，按字符数除以 3 会偏低，导致请求前的预算检查偏乐观。

**改动**
- 新建 `codeharness/tokens.py`：
  - `estimate(text)`：ASCII 字符按 1/4、非 ASCII 字符按 1 计（保守估计）。
  - `Calibrator`：用每次真实返回的 `prompt_tokens / 估算值` 更新指数移动平均（α = 0.3），比例限制在 [0.5, 3.0]；会话恢复时可以从事件中重建。
- `runtime.py`、`models.py` 改用该模块；`model_request` 事件增加 `estimated_input` 字段。
- `benchmark.diagnostics` 增加 `estimate_error = mean(|估算 − 实际| / 实际)`。

**测试**：纯中文、纯 ASCII、混合文本的估算单调且偏保守；校准器收敛且受上下限约束；旧事件中没有 `estimated_input` 时不报错。

**验收**：测试通过；S13 实测中校准后的 `estimate_error < 15%`。

**阶段 2 收尾**：全量回归 + HANDOFF 交接单。

---

## 阶段 3：存储与规模

### S7 运行时内存态、存储去重与检查点差量

**问题**
- 每轮循环都通过 `store.messages()`、`store.events()`、`store.usage()` 全量读取并反序列化会话的所有事件，开销随回合数平方增长。
- 每个 `model_request` 都存一份完整上下文和工具 schema；每个 `checkpoint` 都存一份全工作区哈希表，数据库体积膨胀很快。

**改动**
- `codeharness/store.py`
  - 新表 `blobs(hash TEXT PRIMARY KEY, content TEXT)`，按内容哈希去重。
  - `model_request` 改为存 `{"message_refs": [...], "tools_ref": ..., "max_tokens": ..., "estimated_input": ...}`；`trace` 读取时展开引用。旧格式的完整消息照常读取。
  - 新表 `usage_totals(root_id PRIMARY KEY, requests, input_tokens, output_tokens, cached_tokens, estimated)`，在同一事务中随 `model_request` / `usage` 事件增量更新，`usage()` 改为 O(1) 查询。旧库首次打开时从事件回填。
  - `checkpoint` 改为差量 `{"base": 事件ID, "changed": {...}, "removed": [...]}`，每 20 个差量写一次全量；新增 `files_at(sid)` 用于重建。`baseline` 和 `verification` 仍存全量。
- `codeharness/runtime.py`
  - 循环开始时一次性加载事件，之后在内存中维护 `messages`、已加载 Skills 和本地计数；SQLite 只负责追加写入。
  - 委派子任务返回后，从 `usage_totals` 刷新共享预算（子任务与父任务共用 root 预算）。

**测试**
- 旧格式会话库（测试中用 SQL 直接构造）可以 `sessions`、`trace`、`resume`，用量统计一致。
- 差量检查点重建结果与全量快照一致；崩溃注入的 4 个阶段测试仍然通过。
- 新增性能测试 `tests/test_scale.py`（设置 `CODEHARNESS_SCALE_TESTS=1` 时运行）：模拟模型连续 300 轮工具调用，第 300 轮的存储耗时不超过第 10 轮的 2 倍，数据库体积较 S0 下降 50% 以上。

**验收**：上述测试通过；trace 输出与改造前在信息上等价。

### S8 文件遍历遵循 `.gitignore`、搜索支持正则

**问题**：`Workspace.files()`、`snapshot`、`search` 用 `os.walk` 全量遍历，只排除 `HIDDEN` 列表，遇到 `dist/`、`build/`、`target/`、数据目录会很慢，也会产生大量无关的搜索结果。

**改动**（`codeharness/tools.py`）
- 工作区是 Git 仓库根目录时，用 `git ls-files -z --cached --others --exclude-standard` 获取文件列表（每次快照调用一次），再套用 `protected()` 过滤；Git 不可用时回退到 `os.walk`，并增加默认忽略目录：`dist`、`build`、`target`、`.tox`、`.mypy_cache`、`.pytest_cache`、`.ruff_cache`、`htmlcov`、`.next`。
- 快照文件数超过 20000 时写入警告事件，并建议缩小工作区。
- `search` 新增参数 `regex: boolean`（模式长度不超过 200）和 `max_results: integer`（默认 40，上限 200）。本机有 `rg` 时优先调用 `rg --json`，并传入受保护路径的排除规则。
- README 补充说明：被 `.gitignore` 忽略的文件变化不计入 `changed_files`。

**测试**：`.gitignore` 中的目录不出现在列表、快照和搜索结果中；非 Git 目录回退正常；正则搜索与 `glob` 组合正确；没有 `rg` 时结果一致。

**验收**：测试通过；fixtures 与 demo 不受影响。

**阶段 3 收尾**：全量回归 + 性能测试 + HANDOFF 交接单。

---

## 阶段 4：工具能力

### S9 `apply_patch` 与 `--disable-tool`

**问题**：目前只有单处替换的 `edit_file` 和只能新建的 `write_file`。跨多处或多文件的修改需要多轮"读取—编辑"，增加请求次数，也更容易出现 sha 过期错误。

**改动**（`codeharness/tools.py`、`codeharness/context.py`、`codeharness/cli.py`、`codeharness/benchmark.py`）
- 新增写工具 `apply_patch(patch: string)`，接受标准统一 diff：
  - 支持修改已有文件、新建文件（`--- /dev/null`）、删除文件（`+++ /dev/null`）。
  - 每个 hunk 的原文（上下文行与删除行）必须在文件中唯一精确匹配，换行与 BOM 的处理与 `edit_file` 一致。
  - **先校验全部文件的全部 hunk，再写入**；写入时先写临时文件再 `os.replace`。任一校验失败则不写入任何文件，并在错误中指出是哪个文件的哪个 hunk。
  - 返回每个文件的 `before_sha256` / `after_sha256` 和 `.py` 语法诊断。
- 系统提示词补充：多处或跨文件修改优先使用 `apply_patch`。
- CLI 与评测新增 `--disable-tool NAME`（可重复），用于工具消融实验。

**测试**：多 hunk、多文件、新建、删除、CRLF/BOM；任一 hunk 不匹配时零写入；越界路径和受保护路径被拒绝；只读子任务不可用。

**验收**：测试通过；S13 中对比 `multi` 套件启用与禁用 `apply_patch` 的平均请求次数。

### S10 同批只读工具并行执行

**问题**：同一批 `tool_calls` 中的多个 `read_file`、`search` 串行执行，在大仓库中耗时明显。

**改动**（`codeharness/runtime.py`、`codeharness/tools.py`、`codeharness/store.py`）
- `Tool` 新增 `parallel_safe: bool = False`；只给内置的 `list_files`、`read_file`、`search`、`check_syntax`、`git_status`、`git_diff` 标记为 `True`。`load_skill`、`read_artifact` 会访问 SQLite 连接，插件工具线程安全性未知，均不标记。
- 当一批调用全部可以并行时：主线程先按顺序写入所有 `tool_started`，再用 `ThreadPoolExecutor(max_workers=4)` 执行，最后由主线程**按原顺序**写入 `tool_finished` 和 `tool` 消息。SQLite 只在主线程访问。
- `tool_started` 事件增加 `effect` 字段；`repair_pending` 对中断的只读工具给出"可安全重新执行"的提示，不再笼统说副作用不确定。

**测试**：用带延迟的模拟只读工具，批次耗时接近最大值而不是总和；消息顺序与调用顺序一致；批次中含写工具时退回串行；并行批次中途崩溃后可以正确恢复。

**验收**：测试通过；全量回归无回退。

**阶段 4 收尾**：全量回归 + HANDOFF 交接单。

---

## 阶段 5：评测证据

### S11 `--repeats` 与统计汇总

**问题**：每个任务只跑 1 次，"委派开 3/5、关 4/5"这类差异无法和模型输出的随机性区分开。

**改动**（`codeharness/benchmark.py`、`tests/test_benchmark.py`）
- 新增 `--repeats N`（默认 1），工作区目录改为 `<task>/<variant>/r<k>`；总预算检查乘以重复次数。
- `summarize` 增加：
  - 每个任务、每个变体的成功率；
  - 整体 pass@1 的均值与标准差（按重复轮次计算）；
  - 配对比较只使用两个变体都完整完成全部重复的任务，给出成功率差值和 bootstrap 95% 置信区间（标准库 `random`，固定种子）；
  - 请求次数、Token、耗时的中位数与 P90。
- 报告记录 `repeats` 和统计口径说明。

**测试**：`summarize` 的单元测试覆盖不完整配对、全部跳过、单次运行等边界；`--repeats 1` 时报告结构向后兼容。

**验收**：测试通过；fixtures 模式不受影响。

### S12 大仓库评测套件

**问题**：`multi` 套件的单个文件只有 0.1～1.5 KB，整个仓库只有几 KB，远低于默认 28000 字符的压缩阈值，因此 `delegate_calls` 和 `compactions` 一直为 0。

**改动**
- 新建 `codeharness/benchmark_large.py`，用固定种子**程序化生成**大仓库任务，避免源码膨胀。每题要求：
  - 80～150 个文件，总量 300～600 KB；
  - 至少 2 个 800～1500 行的长模块，必须分页 `read_file`；
  - 大量命名相近的干扰模块，以及一批应当保持通过的已有测试；
  - 缺陷沿调用链分布在 2～4 个模块中，必须先定位再修改；
  - 独立验收脚本放在工作区之外，与现有夹具一致。
- 首批 4 题：例如插件加载链路的配置优先级、事件总线的重试与去重、多级缓存失效、报表导出的时区与舍入。
- `benchmark.py` 新增 `--suite large`；fixtures 模式下同样验证"初始断言失败、参考修复通过"。
- （可选 S12b）新增 `--suite external --manifest tasks.json`，从清单加载真实仓库任务：`{id, repo, commit, prompt, setup, acceptance}`。优先从纯 Python、测试依赖少的开源库中挑选真实 bugfix 提交反向构造，或使用 SWE-bench Lite 的 Python 子集；依赖环境在工作区外预先准备。

**测试**：`tests/test_benchmark.py` 验证生成结果可复现（同一种子哈希一致）、规模符合约束、fixtures 验证通过。

**验收**：`--mode fixtures --suite large` 全部通过；用默认 `--context-chars` 估算，每题完整读取所需上下文超过阈值的 2 倍。

### S13 真实模型实验矩阵

**前提**：S2～S12、M0 已合入 `main`，S0b 已完成。全部实验通过模型池运行，使用 `--output-tokens 4096`、`--repeats 2`；推理强度与 S0b 一致。

**模型分配**：按现有额度和到期日排定，详见 HANDOFF.md 的额度表。

| 顺序 | 编号 | 实验 | 套件 | 变量 | 回答的问题 | 首选模型（切换链） | 估计用量 |
| --- | --- | --- | --- | --- | --- | --- | --- |
| 1 | E0 | 冒烟 | `discount` | 两个 deepseek 模型各跑 1 次 | 工具调用、usage 和 `cached_tokens` 字段是否正常 | 各自固定 | 2 次，约 30K |
| 2 | E1 | 改进前后 | core + multi | 委派开；对照为 S0b | 改进后成功率、请求次数、截断次数的变化 | deepseek-v4.1-flash（→ flash-1017） | 16 次，约 260K |
| 3 | E4 | 补丁工具 | multi | `--disable-tool apply_patch`；启用组复用 E1 的 multi 部分 | `apply_patch` 是否减少请求次数和编辑错误 | deepseek-v4.1-flash（→ flash-1017） | 6 次，约 130K |
| 4 | E2 | 委派收益 | large 3 题 | 委派开 / 关 | 大仓库中委派是否提高成功率或降低主上下文用量 | deepseek-v4.1-flash-1017（→ flash → qwen3.8-max-0902） | 12 次，约 480K |
| 5 | E3 | 压缩影响 | large 3 题，关委派 | `--context-chars 8000`；28000 组复用 E2 的关委派组 | 压缩对成功率和 Token 的影响 | deepseek-v4.1-flash-1017（→ flash） | 6 次，约 240K |

- deepseek-v4.1-flash：S0b 约 270K + S13 约 405K = 675K，额度 918.74K。
- deepseek-v4.1-flash-1017：S13 约 735K + M0 实测约 15K = 750K，额度 996.95K。
- 两者各留约 25% 余量。估算依据是 glm 实测每题 13K～21K；大仓库每题约 40K 是假设，需要先实测。

**命令模板**（参数名以 M0 实现为准，如有出入，以 README 为准）：
```powershell
python -B -m codeharness.benchmark --mode model --suite multi --repeats 2 --model-pool .codeharness/models.json --models deepseek-v4.1-flash,deepseek-v4.1-flash-1017 --env-file .env --allow-exec --output-tokens 4096 --max-requests 18 --max-tokens 40000 --total-requests 108 --total-tokens 240000 --output .codeharness/benchmarks/s13-e1-multi
```

**用量检查与缩减规则**
1. 每个实验开始前，运行 `python -m codeharness.model_pool status`，确认首选模型的剩余额度 ≥ 估计用量 × 1.15。
2. E2 先用 1 个 large 任务跑 1 次，用实测的单次用量重新估算 E2、E3：
   - 不够时先把 E3 缩到 2 题，再把 E2、E3 的 `--repeats` 降到 1；
   - 如果做完还有余量（总余量 > 200K），再加第 4 个 large 任务。
3. 发生模型切换时，按“对比只在同一模型内进行”处理。缺少同模型对照的部分，在余量允许时补跑对照；不够时在结论中如实标注。

**延期预案**（deepseek-v4.1-flash 到期日 12/13 当天视为不可用）
- 到 12/08 时 S2～S12 若仍未全部合入：先用已合入的版本跑 E1、E4，在报告中注明缺少的步骤。
- 已经错过 12/12：在 S0 提交上用 deepseek-v4.1-flash-1017 重跑 S0b（约 270K），E1、E4 改用 flash-1017；E2、E3 缩为 2 题。

**动作**
- 按 E0 → E1 → E4 → E2 → E3 的顺序执行。
- 每个报告核对 `model`、`success`、`truncations`、`delegate_calls`、`compactions`、`cache_hit_ratio`、`estimate_error`。
- 结果写入 HANDOFF.md 的执行记录。README 实测表注明模型，并使用“均值 / 置信区间，n = 2”的口径。

**验收**
- E2 中至少有部分运行出现 `delegate_calls > 0`；E3 的低阈值组出现 `compactions > 0`。
- 每条结论都附模型、n、置信区间和报告路径。
- n = 2 的统计力有限，不显著的差异如实写“未观察到显著差异”。

**阶段 5 收尾**：HANDOFF 交接单 + README 实测表更新。

---

## 阶段 6：展示

### S14 文档、CI 与简历口径

**改动**
- README 首屏加一张 Mermaid 架构图：CLI → Agent 循环 → Model / Registry（Policy、Hooks）/ Context / Store，以及委派子任务和独立验收。
- `trace` 新增 `--timeline`，输出精简的事件时间线（请求、工具、压缩、委派、验证、结果）；README 附一次 `multi` 任务的时间线示例。
- 新增 `.github/workflows/ci.yml`：`ubuntu-latest` 与 `windows-latest` × Python 3.11 / 3.12 / 3.13，运行单元测试与 `fixtures` 的 `full`、`multi`、`large`；README 添加状态徽章。
- 新增 `README.en.md`，与中文版保持同步。
- 更新本地 `INTERVIEW_PREP.md`（已在 `.gitignore`）：简历只写 S13 中有数据支撑的结论。示例写法："在 4 个 100+ 文件仓库上，开启只读委派后主上下文 Token 下降 X%（n=3，95% CI …）"。
- （可选）提交历史开头的 `hello world`、`test` 两条提交已推送到 `origin/main`，整理需要强制推送，只有在仓库没有其他协作者时才考虑；否则保持现状。

**验收**：CI 全绿；README 中英文一致；面试材料中的每个数字都能在报告中找到来源。

---

## 未纳入本轮的方向（备忘）

- 任意 Shell 工具与操作系统级沙箱（容器、Job Object、seccomp）。
- 多模型路由与基于 LLM 的语义摘要压缩。
- 服务化：任务队列、多租户隔离、并发调度（可作为面试 Q12 的演进路线讲，不在本轮实现）。

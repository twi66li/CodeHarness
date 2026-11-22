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

### 2026-11-22 改进计划启动：执行总清单（Codex 单人串行）

```text
任务：IMPROVEMENT_PLAN 全部步骤；执行者：Codex（单人串行，不使用多 Agent 并行）；协调：用户
基线：7263bb2ed9c8469e54fbf6acef812d7cde5d3bff（main，与 origin/main 一致）；工作区：D:\Code\python\CodeHarness；分支：main
范围：本交接单写入时，只新增或修改了文档、CI 和回归脚本，codeharness/ 与 tests/ 下未改动任何文件
交付：未提交的工作区差异（见“云端已完成”）；状态：全部步骤待执行
验证：scripts/regress.py 的结果解析函数已用模拟 unittest 输出验证；其余均未执行（云端不能启动子进程）
未验证或阻塞：S0 离线回归、ci.yml 首次运行、README 中 Mermaid 图在 GitHub 上的渲染
下一步：Codex 按下方“Codex 开工任务书”从执行总清单第 1 项开始
```

#### 执行总清单

由 Codex 一人按顺序执行。⏰ 表示有额度到期时限。每完成一项，就在本节末尾的“执行记录”中填写结果；新会话从第一个未完成的事项继续。

| # | 时限 | 步骤 | 内容 | 详见 |
| --- | --- | --- | --- | --- |
| 1 | ⏰ 11/23，可选 | G1 | glm-5.3 到期前补跑改进前重复基线 | 本节“G1” |
| 2 | 立即 | S0 | 离线回归、提交、推送，确认 CI 通过 | 本节“S0” |
| 3 | ⏰ 12/12 前，建议紧接 S0 | S0b | 用 deepseek-v4.1-flash 跑改进前基线 | 本节“S0b” |
| 4 | 尽早 | M0 | 模型池：额度台账，额度用完自动切换 | IMPROVEMENT_PLAN M0 |
| 5 | ⏰ 11/24 内，可选 | M0 实测 | 用 qwen3.8-flash 做一次真实切换 | 本节“M0 实测” |
| 6～15 | — | S1 → S2 → S3 → S4 → S5 → S6 → S7 → S8 → S9 → S10 | 运行时、工具、上下文、存储 | IMPROVEMENT_PLAN 对应各节 |
| 16～17 | — | S11 → S12 | 多次运行统计、大仓库评测套件 | IMPROVEMENT_PLAN 对应各节 |
| 18 | ⏰ E1、E4 须在 12/12 前完成 | S13 | 真实模型实验 | IMPROVEMENT_PLAN S13 |
| 19 | — | S14 | 实测表、时间线示例、简历口径 | IMPROVEMENT_PLAN S14 |

**日期检查点**：每次开工先看当前日期（UTC+8）。

- 已过 11/23：跳过 G1。
- 已过 11/24：跳过 M0 实测。
- 已到 12/08 而 S13 还没开始：暂停当前步骤，按 IMPROVEMENT_PLAN S13 的“延期预案”，先用已完成的版本跑 E0、E1、E4，再回来继续剩余步骤。

S13 必须在 M0、S11 完成之后才能开始，所以无论如何，M0 和 S11 要在 12/08 前完成。如果进度紧张，可以把 S11、S12 提前到 S1 之前做。S12 依赖 S8，所以提前时要连 S8 一起提前。调整顺序要写入执行记录。

#### 授权与运行环境

- **用户授权**（用户可在此修改）：
  - 可以在本仓库创建分支、提交、合并到本地 `main`，并推送 `origin main`。
  - 禁止强制推送，禁止改写已推送的历史。
  - 可以按“模型额度与使用规则”调用真实模型。
  - 可以在本机执行测试与评测代码。
- **网络与沙箱**：
  - 运行 Codex 时，需要允许写入 `.git`、访问网络（推送和模型调用都需要），并允许本地回环连接（5 项 HTTP 测试需要）。
  - 历史上曾出现 `.git` 只读和回环受限（`WinError 10013`）。
  - `.git` 不可写或无法联网时：停止需要它的操作，写入执行记录的“待用户决定”，继续其他不受影响的工作。
  - 回环受限时：用 `--skip-loopback` 运行回归，并在记录中注明。
- **凭据**：只放在本地 `.env`，不要写入提交、报告摘要或交接正文。

#### 分支与合并（单人串行）

- 每一步都从最新的本地 `main` 新建分支 `codex/<步骤小写>-<slug>`（例如 `codex/m0-model-pool`、`codex/s1-split-run`），直接在主仓库工作，不需要额外的 worktree。唯一的例外是 S0b，见下文。
- 一步完成并验收后：
  1. `git diff --check`；
  2. 一步一个提交；
  3. 运行 `python -B scripts/regress.py --tag <步骤> --compare <S0 summary>`，结果与 S0 一致（或者差异符合该步的预期）；
  4. `git switch main && git merge --ff-only <分支>`；
  5. 在执行记录填写提交号与 summary 路径，在 IMPROVEMENT_PLAN.md 进度表中把该步标记为完成。
- 每个阶段结束时推送一次 `origin main`，确认 CI 通过，并按 AGENTS.md 的格式在本节下方追加一条阶段交接单。阶段边界为：S0b/M0、S1～S4、S5～S6、S7～S8、S9～S10、S11～S13、S14。
- 涉及 `ModelError` 的顺序：M0 先新增 `status`、`code`、`quota_exhausted` 字段，S2 再在此基础上新增 `truncated` 和 `usage`。
- 新测试文件：M0 → `tests/test_model_pool.py`，S4/S8/S9 → `tests/test_tools.py`，S7 → `tests/test_scale.py`。其余步骤沿用现有测试文件。
- 保持文件原有的换行风格：`codeharness/` 下的 Python 源码是 CRLF，Markdown 是 LF。

#### 模型额度与使用规则

截至 2026-11-22 23:00（UTC+8），来自用户的百炼控制台截图。执行前以控制台为准。

| 模型 | 剩余 / 总额 | 到期 | 用途 | 计划用量 |
| --- | --- | --- | --- | --- |
| glm-5.3 | 294.94K / 1M | 2026-11-23 | G1 改进前重复基线（可选） | ≤ 250K |
| qwen3.8-flash | 41.78K / 1M | 2026-11-25 | M0 真实切换验证（可选） | ≤ 30K |
| qwen3.8-max-0902 | 145.94K / 1M | 2026-12-01 | 切换链末位备用；预计 S13 前到期 | 0 |
| deepseek-v4.1-flash | 918.74K / 1M | 2026-12-13 | S0b，以及 S13 的 E0、E1、E4 | 约 675K |
| deepseek-v4.1-flash-1017 | 996.95K / 1M | 2027-01-17 | M0 切换目标，以及 S13 的 E0、E2、E3 | 约 750K |

1. **额度耗尽的表现。** 截图中每个模型最后一列的开关都是开启的（看起来是“用完即停”）。公开反馈显示，百炼开启“用完即停”后，免费额度耗尽会返回 HTTP 403。当前 `models.py` 把所有 401/403 都当作“访问被拒绝”，评测会停止全部后续任务，不会换模型。M0 负责修复。
2. **M0 合入前的真实调用（G1、S0b）只用单一模型**，并用 `--total-tokens` 把上限封在剩余额度以内。
3. **额度只用于 CodeHarness 评测调用。** Codex 自身使用的模型不占用这些额度。不要把 Codex 本身配置成使用百炼的这几个模型，尤其是两个 deepseek 模型，它们要留给评测。
4. **每次真实调用前在控制台核对剩余额度。** M0 合入后，同步更新 `.codeharness/models.json` 中的 `quota_tokens` 和 `quota_as_of`。
5. **对比只在同一模型内进行。** 自动切换只发生在“对比单元”的边界，即一个任务的委派开、关一组。报告按模型分组。切换后缺少同模型对照时，余量允许时补跑同模型对照，否则在结论中如实标注。
6. **到期日当天视为不可用。** 模型池自动选择时按 UTC+8 保守处理。手动执行的 G1 例外，以控制台实际能否调用为准。
7. **推理强度。** G1 与历史 glm 报告保持一致，使用 `--reasoning-effort low`。deepseek 在 S0b 冒烟中先不传该参数；如果百炼文档确认该模型支持，再让 S0b 与 S13 统一使用同一设置。选择结果写入执行记录。
8. 截图显示这些都是免费额度，且已开启用完即停，所以真实调用不需要另行确认费用，但必须遵守上述规则和各步的停止条件。

#### 云端已完成

- `IMPROVEMENT_PLAN.md`：S0～S14 以及 S0b、M0 的有序计划，每一步都写明改动、测试和验收。
- `scripts/regress.py`：一条命令运行单元测试、`full` 和 `multi` 参考夹具、委派开/关 demo。结果输出到 `.codeharness/regress/<tag>-<时间>/summary.json`，支持 `--compare`、`--skip-loopback`。
- `.github/workflows/ci.yml`：在 Ubuntu 和 Windows、Python 3.11/3.12/3.13 上运行 `scripts/regress.py` 并上传日志，不配置任何模型凭据。
- `README.md`：新增 CI 徽章、Mermaid 架构图、模块职责表和回归脚本说明。`README.en.md` 是对应的英文版，内容以中文版为准。
- 本交接单。

**已确认的事实**
- 下方历史条目里的基线 `47c5c8da…` 是 4 个模块提交之前的旧基线，本轮以 `7263bb2` 为准。
- 已有的真实模型报告都是 glm-5.3、每题只跑 1 次。所有报告中 `delegate_calls = 0`、`compactions = 0`，也就是说委派和压缩还没有任何真实模型证据。
- S13 将改用 deepseek 模型，所以历史 glm 结果不能直接当作 S13 的改进前对照，需要 S0b。

**未提交的新增或修改文件**：`IMPROVEMENT_PLAN.md`、`scripts/regress.py`、`.github/workflows/ci.yml`、`README.md`、`README.en.md`、`HANDOFF.md`。

#### G1（可选，11/23）：glm-5.3 改进前重复基线

到期时间以控制台为准：11/23 当天还能调用就执行；一旦报 403 或 `model_access_denied: true`，立即放弃。这一步只改了文档和脚本，运行时代码与 S0 基线一致，所以可以直接在主仓库执行，排在 S0 之前也没问题：

```powershell
cd D:\Code\python\CodeHarness
python -B -m codeharness.benchmark --mode model --suite core --model glm-5.3 --env-file .env --allow-exec --reasoning-effort low --output-tokens 4096 --total-requests 60 --total-tokens 120000 --output .codeharness/benchmarks/pre-glm-core-r2
python -B -m codeharness.benchmark --mode model --suite multi --model glm-5.3 --env-file .env --allow-exec --reasoning-effort low --output-tokens 4096 --max-requests 18 --max-tokens 40000 --total-requests 54 --total-tokens 120000 --output .codeharness/benchmarks/pre-glm-multi-r2
```

- 预计用量约 130K。跑完后看控制台：glm-5.3 剩余 ≥ 150K 时，用输出目录后缀 `-r3` 再跑一轮，否则停止。
- 这批数据与 11/21 的 `glm53-core-low-20261121`、`glm53-multi-low-20261121` 合在一起，得到 n=2～3 的改进前 glm 数据，只用来估计同一模型重复运行的波动。

#### S0：离线基线

```powershell
cd D:\Code\python\CodeHarness
git status --short --branch
python -B scripts/regress.py --tag s0
```

预期：单元测试 78 项 OK（skipped=1，符号链接）；夹具 `full` 12/12、`multi` 3/3；demo 委派开 8 次请求、关 5 次，均为 `verified`。

- 不符合预期：先排查原因，把结论写入执行记录，不要继续后面的步骤。
- 符合预期：提交并推送：

```powershell
git add IMPROVEMENT_PLAN.md scripts/regress.py .github/workflows/ci.yml README.md README.en.md HANDOFF.md
git commit -m "docs: 新增改进计划、离线回归脚本、CI 与英文 README"
git push origin main
```

推送后：
1. 新提交号记为 **S0 提交**。
2. `.codeharness/regress/s0-<时间>/summary.json` 的绝对路径记为 **S0 summary**。
3. 在 GitHub Actions 确认 CI 全部通过。失败时记录失败的矩阵项和日志摘要；属于环境差异的，修复 `ci.yml` 后重新推送。
4. 在 IMPROVEMENT_PLAN.md 进度表中把 S0 标记为完成。

#### S0b：deepseek-v4.1-flash 改进前基线（12/12 前）

S13 的改进前后对比必须用同一个模型，所以要在 S0 提交上用 deepseek-v4.1-flash 先跑一遍。这里用临时 worktree，好让 `main` 可以照常往前推进。

```powershell
git -C D:\Code\python\CodeHarness worktree add --detach D:\wt\ch-pre <S0 提交>
cd D:\wt\ch-pre
$envf = "D:\Code\python\CodeHarness\.env"
$out = "D:\Code\python\CodeHarness\.codeharness\benchmarks"
# 1) 冒烟：确认工具调用、usage 和独立验收都正常
python -B -m codeharness.benchmark --mode model --task discount --model deepseek-v4.1-flash --env-file $envf --allow-exec --output-tokens 4096 --total-requests 12 --total-tokens 24000 --output "$out\pre-ds-smoke"
# 2) 冒烟通过后，跑两轮 core + multi
foreach ($r in 1, 2) {
  python -B -m codeharness.benchmark --mode model --suite core --model deepseek-v4.1-flash --env-file $envf --allow-exec --output-tokens 4096 --total-requests 60 --total-tokens 120000 --output "$out\pre-ds-core-r$r"
  python -B -m codeharness.benchmark --mode model --suite multi --model deepseek-v4.1-flash --env-file $envf --allow-exec --output-tokens 4096 --max-requests 18 --max-tokens 40000 --total-requests 54 --total-tokens 120000 --output "$out\pre-ds-multi-r$r"
}
cd D:\Code\python\CodeHarness
git worktree remove D:\wt\ch-pre
```

预计用量约 270K（按 glm 实测每题 13K～21K 估算，以冒烟的实测结果校正）。

**停止条件**
- **冒烟未通过**（工具调用格式不兼容、模型名错误、usage 缺失等）：停止 S0b，记录错误，先做 M0；需要改运行时才能兼容的，放到对应步骤里处理。处理完之后，仍然要在 S0 提交上重跑 S0b。如果做不到，就在记录中说明。
- **任一报告出现 `model_access_denied: true`**：立即停止。用 `python -m codeharness trace <session_id> --workspace <该用例的 repo 目录> --store <该用例的 state.sqlite3> --json` 找到 `model_error` 事件，把 HTTP 状态码和括号里的错误码写入执行记录，M0 用它识别额度耗尽。
- **用量**：每轮结束后看控制台余额，累计超过 320K 就不再跑剩下的部分。

推理强度的选择按“模型额度与使用规则”第 7 条处理，并写入执行记录。

#### M0 实测（可选，11/24 内，M0 合入本地 `main` 后）

在主仓库执行：

1. 复制 `models.example.json` 为 `.codeharness/models.json`。用控制台数字更新所有 `quota_tokens`，把 `quota_as_of` 设为当前时间（UTC+8）。
2. 临时给 qwen3.8-flash 加上 `"cap_tokens": 30000`。
3. 执行：
   ```powershell
   python -m codeharness.model_pool status --config .codeharness/models.json
   python -B -m codeharness.benchmark --mode model --task discount --model-pool .codeharness/models.json --models qwen3.8-flash,deepseek-v4.1-flash-1017 --env-file .env --allow-exec --output-tokens 4096 --total-requests 12 --total-tokens 24000 --output .codeharness/benchmarks/m0-switch-1
   python -B -m codeharness.benchmark --mode model --task discount --model-pool .codeharness/models.json --models qwen3.8-flash,deepseek-v4.1-flash-1017 --env-file .env --allow-exec --output-tokens 4096 --total-requests 12 --total-tokens 24000 --output .codeharness/benchmarks/m0-switch-2
   python -m codeharness.model_pool status --config .codeharness/models.json
   ```
4. 预期：第 1 次在 qwen3.8-flash 上运行；第 2 次开始前，因为 qwen3.8-flash 的剩余额度不足一个用例的预算，自动切到 deepseek-v4.1-flash-1017。报告中的 `model` 字段与 `status` 输出一致。
5. 结束后删除 `cap_tokens`。
6. 真实的“403 耗尽后切换”不做实测，只靠离线测试覆盖；S0b 如果碰到真实的耗尽错误码，补进 `quota_error_codes`。

#### Codex 开工任务书（首次发送）

```text
你是 CodeHarness 仓库的唯一执行者，按顺序完成本轮改进计划的全部步骤，包括开发、测试、真实模型评测和文档收尾。
仓库：D:\Code\python\CodeHarness（GitHub：twi66li/CodeHarness），Python 3.11+，运行时只用标准库。

开工：
1. 依次阅读 AGENTS.md、HANDOFF.md 中“2026-11-22 改进计划启动”一节的全部内容、IMPROVEMENT_PLAN.md。以当前源码、Git 状态和 HANDOFF“执行记录”为准。
2. 检查当前日期（UTC+8），按“日期检查点”决定是否跳过 G1、M0 实测，或者改为先做 S13 的延期预案。
3. 从执行总清单中第一个未完成的事项开始，逐项执行。

每一步的做法：
- 按 IMPROVEMENT_PLAN.md 对应一节的“改动”“测试”“验收”执行：先写失败的测试，再实现。只改该步需要的文件，不顺手重构。
- 按 HANDOFF“分支与合并”建分支、提交、运行 scripts/regress.py --compare，快进合入本地 main。
- 涉及事件格式的步骤（S2、S5、S6、S7、S10），必须附“旧格式会话仍可 sessions/trace/resume”的测试。
- S1 是纯重构：回归结果必须与 S0 完全一致，demo 请求次数仍为 8 / 5。
- M0 的 ModelPool 实现现有的 Model 协议。按已确认的接入点在 runtime 记账前完成选模，后续步骤应保持每个物理请求可单独追溯。
- 每完成一步，立即更新 HANDOFF“执行记录”和 IMPROVEMENT_PLAN 进度表，然后继续下一步，不需要等待确认。
- 阶段结束时推送 origin main，确认 CI 通过，并按 AGENTS.md 的格式追加阶段交接单。

真实模型调用（只在 G1、S0b、M0 实测、S13 中进行）：
- 严格遵守 HANDOFF“模型额度与使用规则”和各步的停止条件。每次调用前在百炼控制台或 model_pool status 中核对剩余额度。
- 开发和测试过程中一律使用假模型，不使用 .env。
- 凭据不要写入任何提交、报告摘要或交接正文。

遇到以下情况，写入执行记录的“待用户决定”，然后继续其他不受影响的事项：
- 额度不足以完成必需的实验；
- .git 不可写或无法联网；
- 某一步的验收标准无法满足，且原因不在本步范围内；
- 需要偏离 IMPROVEMENT_PLAN 的设计。

不要做：强制推送、改写已推送历史、修改 benchmark_tasks.py 中已有任务的题面与验收、把 .env 或会话库加入 Git。
```

#### Codex 续作提示词（新会话或中断后发送）

```text
继续 CodeHarness 改进计划。先读 AGENTS.md、HANDOFF.md 中“2026-11-22 改进计划启动”一节（重点看执行记录和日期检查点）、IMPROVEMENT_PLAN.md，然后运行 git status --short --branch 和 git log --oneline -5，核对执行记录与实际 Git 状态是否一致：
- 有未完成的分支或未提交改动：先确认它属于哪一步，再继续该步；
- 状态一致：从执行总清单中第一个未完成的事项继续。
规则与首次任务书相同，以 HANDOFF 中的“Codex 开工任务书”为准。
```

#### 执行记录

| 事项 | 状态 | 结果与证据 |
| --- | --- | --- |
| G1 glm-5.3 重复基线 | ☑ | `low`、输出上限 4096。[core r2](.codeharness/benchmarks/pre-glm-core-r2/report.json) 5/5，32 次，60,556 Token。[multi r2](.codeharness/benchmarks/pre-glm-multi-r2/report.json) 2/3，25 次，75,467 Token，`ledger-reconcile` 耗尽单题预算。合计 136,023 Token，按本轮用量再跑完整一轮会超过 G1 的 250K 总上限。两套件均未触发委派或压缩。 |
| S0 | ☑ | 基线提交 `1a912f53c6749ba38d9b37e68a1eb129434e6151` 已推送。[S0 summary](.codeharness/regress/s0-20261122-232004/summary.json)。Windows / Python 3.13.12，78 项中 77 通过、1 项符号链接因权限跳过；12/12 + 3/3 夹具通过，离线 demo 为 8/5 次请求且均 verified。初次 CI 在 Windows 输出中文时编码失败，设置 UTF-8 后 [六个矩阵作业全部通过](https://github.com/twi66li/CodeHarness/actions/runs/45038344148)，日志和摘要均已上传。 |
| S0b | ☑ | 在 `1a912f5` 使用 `deepseek-v4.1-flash` 默认推理强度。[冒烟](.codeharness/benchmarks/pre-ds-smoke/report.json) 1/1、10,570 Token。[core r1](.codeharness/benchmarks/pre-ds-core-r1/report.json) 5/5、82,107 Token。[multi r1](.codeharness/benchmarks/pre-ds-multi-r1/report.json) 3/3、102,124 Token。[core r2](.codeharness/benchmarks/pre-ds-core-r2/report.json) 5/5、77,937 Token。[multi r2](.codeharness/benchmarks/pre-ds-multi-r2/report.json) 先完成 1 题、36,506 Token。用户批准把 S0b 上限提高到 400K 后，只补跑了 [rbac-gateway](.codeharness/benchmarks/pre-ds-multi-r2-rbac-gateway/report.json) 和 [ledger-reconcile](.codeharness/benchmarks/pre-ds-multi-r2-ledger-reconcile/report.json)，独立验收均通过，分别用了 35,895 和 36,253 Token。两轮共 16/16，加冒烟共 111 次请求、381,392 Token，无模型错误或访问拒绝，委派 0 次，压缩 1 次。 |
| M0 | ☑ | `048750dc119f426389e15be4ff7b4eecc5162711` 已推送。[回归摘要](.codeharness/regress/m0-20261122-234304/summary.json) 中 83 项测试，82 通过、1 项符号链接跳过，夹具 12/12 + 3/3，demo 8/5。[CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45039928635)。发起请求前选定模型，额度拒绝通过现有重试回路切换，trace 按物理请求记模型和用量。 |
| M0 实测 | ☐ | 待确认 `qwen3.8-flash` 和 `deepseek-v4.1-flash-1017` 额度；S1 可使用假模型独立推进。 |
| S1 | ☑ | 本地快进合并 `707f8496ee9ccd87b8c05427596e76876981d3a2`。[回归摘要](.codeharness/regress/s1-20261122-234735/summary.json)。`Agent.run` 26 行，最长拆出方法 51 行。83 项中 82 通过、1 跳过，夹具和 demo 结果与 S0 一致。待阶段推送。 |
| S2 | ☑ | 本地快进合并 `8e51318d8fea9734e1b42615392b57785b8dfb06`。[回归摘要](.codeharness/regress/s2-20261122-235055/summary.json)。86 项中 85 通过、1 跳过，已验证截断恢复、原样记账及旧会话继续执行。待阶段推送。 |
| S3 | ☐ | |
| S4 | ☐ | |
| S5 | ☐ | |
| S6 | ☐ | |
| S7 | ☐ | |
| S8 | ☐ | |
| S9 | ☐ | |
| S10 | ☐ | |
| S11 | ☐ | |
| S12 | ☐ | |
| S13 | ☐ | 各实验的报告目录、模型、n、主要结论 |
| S14 | ☐ | |
| 顺序调整 | — | S0b 因原累计上限跳过两题，M0 开发期间经用户批准在固定基线上补齐。M0 实测待额度确认，S1 先行。 |
| 待用户决定 | — | |

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

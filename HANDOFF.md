# CodeHarness 交接记录（HANDOFF）

接手本仓库开发前，请按 [AGENTS.md](AGENTS.md) 核对 `git status --short --branch` 与 `git rev-parse HEAD`，以实际源码和实测为准。

## 验收与修复清单｜2026-11-24 G1～G8（H1～H6，Codex 单人串行）

```text
验收人：AWS Quick（云端，只读审查：代码、27 条坏补丁样本、报告与会话库、GitHub CI 页面）
基线：059d3cc（main 与 origin/main 一致）；工作区：D:\Code\python\CodeHarness
结论：大体通过。G1、G3、G4、G5、G6、G7、G8 通过；G2 部分通过（剩余 4 条失败的原因判断有误）
真实调用：本清单全部离线完成，不需要调用模型
状态：H1～H6 已完成并推送。代码、CI 和 README 的验收提交为 c7acc9e，CI 六组合全部通过。
```

### 验收结论

| 项 | 结论 | 说明 |
| --- | --- | --- |
| G1 | 通过 | 27 条全部还原；样本中没有绝对路径、用户名或密钥 |
| G2 | **部分通过** | 不再按声明行数读取、按上下文唯一匹配、行号只用于多处匹配时选最近一处、拒绝时给出具体原因，都已实现；回放 6/27 → 23/27。剩余 4 条的原因判断有误，见 H1 |
| G3 | 通过 | 系统提示词中已删除“优先使用 apply_patch”，工具说明改为中性描述 |
| G4 | 通过 | 模型名允许 `/`、`:`，拒绝 `..`；评测目录名用 `quote()` 转义 |
| G5 | 通过 | 没有 Skill 时不注册 `load_skill`，也不出现 Skills 段落；demo 仍为 8/5 次请求 |
| G6 | 通过，记录不全 | `core` 5/5；`multi` 开、关补丁均 6/6，Token 中位数 57,651 / 56,726。开补丁组补丁成功 3 次、失败 1 次，这一点没有写入执行记录；任务要求的 `compare` 也没有运行 |
| G7 | 通过，记录不全 | 新夹具参考验收 1/1；试探时开、关委派**都是 0/1**，都耗尽了 12 万预算，委派 0 次。按门槛停止是对的，但执行记录没写两次都失败 |
| G8 | 通过 | [最终 CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45240828149)；本地回归 129 项中 127 项通过、2 项按设计跳过 |

G6 与 G7 合计约 102 万 Token，在 300 万上限之内。

**剩余 4 条坏补丁的真实原因**（`tests/test_real_patches.py` 中的注释写的是“021/025 的原文与目标文件不符”，逐行核对后**不成立**，这两条的原文与文件完全一致）：

| 样本 | 真实原因 |
| --- | --- |
| 021 | 第 2、3 个文件只有 `--- a/app/policies.py`、`--- a/app/gateway.py`，没有 `+++` 行。解析器把 `--- a/...` 当成片段里的一条删除行，拼进了上一个文件的片段，最后报“未找到原文”，这个报错也误导了模型 |
| 025 | 补丁最后一行是 `--- End Patch`，目前只识别 `*** End Patch`，这一行同样被当成删除行 |
| 001、002 | 使用 `*** Begin Patch` / `*** Update File: <路径>` / `*** End Patch` 格式（OpenAI 风格）。G6 中唯一一次补丁失败（“补丁第 1 行缺少成对的文件头”）也是这种格式，累计已出现 3 次 |

**工作区中尚未提交的改动**（11-24 16:25～16:30，从新建的 `CLAUDE.md`、`.claudeignore` 判断来自一个 Claude Code 会话）：`HANDOFF.md` 和 `IMPROVEMENT_PLAN.md` 被精简（完整版本在 `059d3cc` 中），`README.md` 删除了 S13 带置信区间的对照表，新增 `CLAUDE.md` 和 `.claudeignore`，`INTERVIEW_PREP.md` 已不在仓库目录中（用户确认不需要还原）。按 AGENTS.md 的规定，**不要丢弃或覆盖这些改动**，处理方式见 H4。

### 修复清单

| # | 级别 | 事项 | 改动范围 | 验收 |
| --- | --- | --- | --- | --- |
| H1 | 必须 | **补丁格式兼容（三类）**：① **缺少 `+++` 行**：`--- <路径>` 的下一行直接是 `@@` 时，把这一行当作文件头（新旧路径相同）。在片段内部，`--- <路径>` 只有同时满足两个条件才视为下一个文件头：下一行是 `+++ ` 或 `@@`，且路径是 `/dev/null` 或工作区内存在的文件；否则仍按删除行处理（避免把真正以 `--` 开头的代码行当成文件头，例如 SQL 注释）。② **结束标记**：补丁末尾的 `*** End Patch` 和 `--- End Patch` 都忽略。③ **OpenAI 风格**：支持 `*** Begin Patch`、`*** Update File: <路径>`、`*** Add File: <路径>`、`*** Delete File: <路径>`、`*** End Patch`；`Update File` 下面的 `@@` 片段按现有规则解析（上下文唯一匹配）；`Add File` 的正文全部是 `+` 行；`Delete File` 删除整个文件。`*** Move to:` 不支持，遇到时返回明确的错误。不变的底线：上下文必须唯一匹配，先校验全部再写入，失败回滚，CRLF/BOM 保持原样 | `codeharness/tools.py`、`tests/test_tools.py` | `tests/test_tools.py` 中每一类各加一个测试，另加一个“`--- ` 开头的真实代码行仍按删除行处理”的测试；回归结果与上次一致 |
| H2 | 必须 | **加强真实补丁回放测试**：①期望全部 27 条都能应用，去掉例外名单；如果仍有失败，逐条写明原因（必须是补丁本身内容有误，而不是格式问题），并把原因写进对应的 `meta.json`；②应用成功后，对改动过的 `.py` 文件做 `ast.parse`，语法必须正确；③修正测试里关于 021/025 的错误注释 | `tests/test_real_patches.py`、`tests/fixtures/real_patches/*/meta.json` | 执行记录中写明回放通过数（预期 27/27）和语法检查结果 |
| H3 | 必须 | **补齐 G6、G7 的执行记录**：①G6 写明开补丁组补丁成功 3 次、失败 1 次（失败为 OpenAI 风格格式），并运行 `python -m codeharness.benchmark compare --baseline .codeharness/benchmarks/magpie-g6-patch-on/report.json --treatment .codeharness/benchmarks/magpie-g6-patch-off/report.json` 和 `--baseline .codeharness/benchmarks/magpie-e4-after/report.json --treatment .codeharness/benchmarks/magpie-g6-patch-on/report.json`，结果写入记录；②G7 写明试探结果为开、关委派都是 0/1，都耗尽了 12 万预算 | `HANDOFF.md` | 记录中的数字能和报告对上 |
| H4 | 必须 | **处理工作区中尚未提交的改动**：①先运行 `git status` 和 `git diff --stat`，把这些改动列进执行记录，并**向用户确认是否一并提交**；未经确认，不要提交、丢弃或覆盖。②无论用户如何决定，都修正以下错误：`IMPROVEMENT_PLAN.md` 中 S4 的提交号 `02b67f57` 应为 `02b6f571`；`CLAUDE.md` 中的测试命令写成了 `pytest`，本项目测试使用 `unittest`，应改为 `python -B -m unittest tests.test_runtime -v` 之类的写法，并删掉“未在此核实”“仅据文件名推断”这些已不再准确的说明（`model_pool.py`、`tokens.py`、`benchmark*.py` 的职责见 README）。③建议在 README 中恢复 S13 的同模型对照表（`059d3cc` 中有），因为“`multi` 6/6 → 3/6”这类结论需要置信区间支撑；是否恢复由用户决定 | `IMPROVEMENT_PLAN.md`、`CLAUDE.md`，以及 README（取决于用户决定） | 执行记录中写明用户的决定和最终提交了哪些文件 |
| H5 | 建议 | **CI 的 Node.js 20 弃用警告**：把 `.github/workflows/ci.yml` 中的 `actions/checkout`、`actions/setup-python`、`actions/upload-artifact` 升级到在 Node.js 24 上运行的主版本（以各 action 发布页为准） | `.github/workflows/ci.yml` | CI 6/6，且没有 Node.js 20 弃用警告 |
| H6 | 必须 | **收尾**：README 中英文版的补丁回放数字改为 H2 的结果，并在 `apply_patch` 说明中写明支持的三种格式；推送 `origin main`，确认 CI 6/6 | README、`HANDOFF.md` | CI 链接写入执行记录 |

### 执行规则

- 顺序：H1 → H2 → H3 → H4（等待用户确认期间可以先做 H5）→ H5 → H6。
- 每一步：从最新 `main` 新建分支 `codex/h<N>-<slug>`，先写失败的测试再实现，一步一个提交，运行 `python -B scripts/regress.py --tag h<N> --compare <S0 summary>`，然后快进合入本地 `main`。
- 本清单不调用真实模型。
- 未提交的改动属于另一个会话，未经用户确认不要提交、丢弃或覆盖；需要修改 `HANDOFF.md` 时，只追加内容，不要删除已有段落。

### Codex 任务书（直接发送）

```text
继续 CodeHarness。先读 AGENTS.md，以及 HANDOFF.md 中的“验收与修复清单｜2026-11-24 G1～G8”一节，然后运行 git status --short --branch 和 git log --oneline -5，确认 main 为 059d3cc 或其后续提交。工作区里有另一个会话留下的未提交改动，未经用户确认不要提交、丢弃或覆盖。

按 H1～H6 的顺序执行，遵守“执行规则”。每完成一项，在本节末尾的“执行记录”中填写提交号、回归摘要路径和关键数字，然后继续下一项。H4 需要用户决定的地方，先把问题写进“待用户决定”，再继续 H5。本清单不调用真实模型。
```

### 执行记录

| 事项 | 状态 | 提交与证据 |
| --- | --- | --- |
| H1 | ☑ | `6c48acc`。三类格式和 SQL 删除行歧义的定向测试 13/13。[回归](.codeharness/regress/h1-20261124-170624/summary.json) |
| H2 | ☑ | `926bb5f`。27/27 条补丁应用成功，80 次 Python 文件 `ast.parse` 全通过。回归 133 项中 131 项通过、2 项跳过，夹具 19/19，demo 请求数为 8/5。[回归](.codeharness/regress/h2-20261124-170756/summary.json) |
| H3 | ☑ | `2ba0ea1`。G6 启用组补丁成功 3 次、失败 1 次，会话事件确认失败请求使用 OpenAI 格式。G7 启用和禁用委派各 0/1，均触发单题 120,000 Token 预算停止，委派调用各 0 次。[G6 启用报告](.codeharness/benchmarks/magpie-g6-patch-on/report.json) · [G7 试探报告](.codeharness/benchmarks/magpie-g7-probe/report.json) |
| H4 | ☑ | `6045268`。开工时有 `.gitignore`、`HANDOFF.md`、`IMPROVEMENT_PLAN.md`、`README.md` 既有改动，以及未跟踪的 `.claudeignore` 和 `CLAUDE.md`。按用户决定删除两份 Claude 文件，采用最新交接与计划，保留中文 README 精简版，`.gitignore` 留在本地。S4 提交号已更正为 `02b6f571`。本轮提交的文档为 `HANDOFF.md`、`IMPROVEMENT_PLAN.md`、`README.md`、`README.en.md`。 |
| H5 | ☑ | `aa1697b`。升级 `checkout@v5`、`setup-python@v6`、`upload-artifact@v6`。六个作业的日志均确认使用新版本，日志和作业注解中均无 Node.js 20 弃用警告。[CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45363116517) |
| H6 | ☑ | `c7acc9e` 已推送到 `origin/main`，中英文 README 已更新补丁格式、27/27 回放和本地回归数字。CI 在 Ubuntu、Windows 的 Python 3.11～3.13 上全部通过。[CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45363116517) |
| 待用户决定 | — | H4 的文档处理方式已确认。 |

两次公开 CLI `compare` 均比较同一 Magpie 模型的 3 道题、6 个配对，两侧未配对数均为 0。下表各差值按对照后的结果减去基线计算。

| 对照 | 独立验收 | 成功率差及 95% 置信区间（百分点） | 请求差中位数 | Token 差中位数 |
| --- | --- | --- | ---: | ---: |
| G6 启用补丁 → 禁用补丁 | 6/6 → 6/6 | 0 `[0, 0]` | 0 | −403 |
| Magpie E4 改后 → G6 启用补丁 | 6/6 → 6/6 | 0 `[0, 0]` | 0 | +1,947.5 |

输入报告见 [Magpie E4 改后](.codeharness/benchmarks/magpie-e4-after/report.json) 和 [G6 禁用补丁](.codeharness/benchmarks/magpie-g6-patch-off/report.json)。

---

## 最新阶段｜2026-11-24 补丁收尾、委派评测与遗留问题（G1～G8）

- **当前基线**：`059d3cc`（`main` 与 `origin/main` 一致）；工作区：`D:\Code\python\CodeHarness`
- **真实调用渠道**：本机 Magpie（`--env-file .env`，默认 `workbuddy/deepseek-v4.1-flash`）
- **状态**：G1～G6 与 G8 已完成并验收（[最终 CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45240828149)）；G7 试探按门槛停止。

### 执行记录

| 事项 | 状态 | 提交与证据 |
| --- | --- | --- |
| G1 | ☑ | `d7ece9c`。真实失败 27 条全部还原，基线回放 6/27。[回归](.codeharness/regress/g1-20261124-021847/summary.json) |
| G2 | ☑ | `8102fe7`。`apply_patch` 行号容错（不按声明行数截断，按上下文唯一匹配+行号消歧），回放通过 23/27。[回归](.codeharness/regress/g2-20261124-022105/summary.json) |
| G3 | ☑ | `79c9a60`。系统提示词不再优先推荐 `apply_patch`，前缀缓存和回归通过。[回归](.codeharness/regress/g3-20261124-022227/summary.json) |
| G4 | ☑ | `7d2fb33`。`ModelPool` 与评测目录支持含 `/`、`:` 的模型名（如 `workbuddy/deepseek-v4.1-flash`）。[回归](.codeharness/regress/g4-20261124-022343/summary.json) |
| G5 | ☑ | `da41c69`。工作区无 Skill 时不注册 `load_skill`，单元测试 126 通过、2 跳过。[G1～G5 CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45238299420) |
| G6 | ☑ | `da41c69`。同渠道复测（共 792,592 Token）：`core` 5/5；`multi` 启用/禁用补丁均 6/6，请求中位数均为 10。[core](.codeharness/benchmarks/magpie-g6-core/report.json) · [启用](.codeharness/benchmarks/magpie-g6-patch-on/report.json) · [禁用](.codeharness/benchmarks/magpie-g6-patch-off/report.json) |
| G7 | ◐ | `61b42bc`。新增固定种子 `investigate-*` 夹具（220 文件，夹具 1/1，回归 127 通过、2 跳过）。试探 1 题开关各 1 次共 229,061 Token，开放组实际委派 0，按门槛未放行两轮配对。[夹具](.codeharness/benchmarks/g7-investigation-fixtures/report.json) · [试探](.codeharness/benchmarks/magpie-g7-probe/report.json) |
| G8 | ☑ | `059d3cc` 已推送 `origin main`，中英文 README 与计划同步。[最终 CI 6/6](https://github.com/twi66li/CodeHarness/actions/runs/45240828149) |
| 待用户决定 | — | G7 普通任务仍未自发委派，缺少估计委派收益的样本（后续可按需决定是否调整提示词或任务设计）。 |

---

## 开发阶段统一用模约定（2026-11-24 起）

- **默认渠道**：仓库根目录 `.env`（与 `.env.magpie` 一致）已切为 `CODEHARNESS_BASE_URL=http://127.0.0.1:3425/v1`、`CODEHARNESS_MODEL=workbuddy/deepseek-v4.1-flash`，真实调用直接传 `--env-file .env` 即可；如需切其他模型，用 `--model <magpie模型ID>` 覆盖。原百炼配置备份在本地 `.env.bailian`（当前暂停使用）。
- **离线开发不变**：单元测试、`--mode fixtures`、`demo` 和 `scripts/regress.py` 保持零真实调用，不读取 `.env`。
- **运行前提**：发起真实调用前确认本机 Magpie 运行中（`127.0.0.1:3425` 可连）。
- **对比口径**：后续改进评测在 `workbuddy/deepseek-v4.1-flash` 上做同渠道改前/改后或开/关配对，不与历史百炼报告混比。

*(注：更早期的 S0～S14 及 Day 1～7 历史交接记录已归档于 Git 历史中。)*

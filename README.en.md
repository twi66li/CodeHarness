# CodeHarness

[![CI](https://github.com/twi66li/CodeHarness/actions/workflows/ci.yml/badge.svg)](https://github.com/twi66li/CodeHarness/actions/workflows/ci.yml)

An extensible, inspectable coding-agent runtime written in Python. Python 3.11+, standard library only at runtime.

[中文](README.md) · This file mirrors the Chinese README; when they differ, the Chinese version is authoritative.

## Architecture

```mermaid
flowchart LR
    CLI["cli.py<br/>run / resume / demo / sessions / trace"] --> Agent
    Bench["benchmark.py<br/>fixtures / model evaluation"] --> Agent
    Bench --> Accept["Independent acceptance scripts<br/>outside the agent workspace"]

    subgraph Agent["runtime.Agent shared execution loop"]
        direction TB
        Budget["Request / token / time budget checks"] --> Prepare["Context.prepare<br/>keep user messages and recent turns"]
        Prepare --> Call["Model.complete<br/>bounded retry and backoff"]
        Call --> Batch["Execute tool_calls batch"]
        Batch --> Check["checkpoint / verification"]
        Check --> Budget
    end

    Call --> Model["models.ChatModel<br/>Chat Completions compatible"]
    Prepare --> Ctx["context.Context<br/>AGENTS.md · Skills · compaction"]
    Batch --> Reg["tools.Registry<br/>schema check → before hooks → Policy → execute → after hooks"]
    Reg --> WS["tools.Workspace<br/>path boundary · protected files · sha256 snapshots"]
    Batch -- delegate --> Child["Read-only worker<br/>same loop · own context · shared root budget · ≤6 requests"]
    Agent --> Store[("store.Store · SQLite<br/>sessions · append-only events · artifacts")]
    Store -. resume / repair_pending .-> Agent
```

| Module | Responsibility |
| --- | --- |
| `runtime.py` | Execution loop, budgets and timeouts, retries, tool batches, read-only delegation, final status and verification |
| `models.py` | Model protocol and Chat Completions adapter: error classification, `Retry-After`, response sanitising |
| `tools.py` | Workspace path boundary, permission policy, tool registry and argument validation, built-in file/search/test/Git tools |
| `context.py` | System prompt, `AGENTS.md` and Skills loading, compaction of older turns above a threshold |
| `store.py` | SQLite append-only events, paged artifacts, usage totals, reconciliation of interrupted tool calls |
| `benchmark.py` / `benchmark_tasks.py` | Independent-acceptance evaluation, delegation ablation, business fixtures |

## Running

```powershell
python -m codeharness demo
python -m unittest discover -s tests -v
```

`demo` runs read-only delegation → locate → failing test → edit → verify in a fresh directory.
It uses a deterministic adapter and never calls a real model, so it says nothing about model fix rates.

To use any Chat Completions compatible endpoint with native tool calling, copy `.env.example` into a local `.env`.

```powershell
python -m codeharness run "Add a feature to the project and verify it" --workspace D:/your/repo --env-file .env
```

Write and test-execution permissions are asked for each time by default. Non-interactive environments must pass `--allow-write` and `--allow-exec` explicitly.
`--isolate` creates a separate worktree from HEAD of a clean Git repository and keeps the result for inspection.
`--no-delegate` disables read-only exploration workers; `--model-attempts` sets the maximum attempts per model turn (default 3, including the first request).

```powershell
python -m codeharness sessions --workspace D:/your/repo
python -m codeharness resume SESSION_ID --workspace D:/your/repo --env-file .env
python -m codeharness trace SESSION_ID --workspace D:/your/repo --json
```

## How it works

- The main task and read-only workers share one execution loop and one request/token budget; a worker has its own context and at most 6 requests.
- Model requests and retries share the budget. 429, common transient 5xx and retryable connection errors are retried a bounded number of times, honouring `Retry-After` or exponential backoff. Permission and authentication failures end the task and are never bypassed.
- Tools are registered centrally and declare an effect (`read` / `write` / `execute` / `delegate`). Edits check SHA-256 and reject stale content and paths outside the workspace; writing or editing a `.py` file returns a non-blocking syntax diagnostic.
- Search supports globs (including `**/`), single-file `unittest`, and non-executing `check_syntax`. At a Git repository root, read-only `git_status` and `git_diff` are available; diffs are against HEAD, cover visible tracked files only, and can be narrowed by path when long.
- SQLite records model inputs, tool results, usage and status as append-only events; long outputs are stored as artifacts and read page by page.
- On resume, interrupted tool calls are reconciled and file changes are checked; write operations with unknown outcomes are never replayed automatically.
- Above a threshold, older complete turns are compacted while every user message and the latest turns are kept. This is not a semantic summary.
- `AGENTS.md` at the project root supplies rules; the body of `.codeharness/skills/<name>/SKILL.md` is loaded on demand.
  A Skill can carry `description: short text` between `---` lines; the directory name is the call name.
- `--plugin examples/line_count.py` demonstrates a trusted Python tool extension; the registry also exposes `before` / `after` hooks.

`verified` only means the last test run in the current workspace passed and file contents are unchanged since; a later failing or incomplete test run invalidates it. It does not replace independent acceptance.
Token budgets are estimated before a request and corrected from `usage` afterwards. Only failed attempts that may have produced output (5xx, timeouts, length truncation) conservatively reserve the estimated input plus the output cap and are marked `estimated`; failures that clearly produced nothing (429, auth denial) do not consume output budget but still count towards the shared request limit. This is not a provider-side billing cap.
Each model attempt and test run uses the task's remaining time, capped at 60 seconds each; Git queries are capped at 15 seconds. Timeouts are checked at call boundaries and cannot guarantee immediate termination of every host process.
Tests run on the local machine; path checks, permissions and Git worktrees are not an OS sandbox.
Extensions are trusted local Python code with host privileges; read-only workers never load custom extensions.
There is currently no arbitrary shell, no parallel writes and no third-party plugin compatibility.

A model adapter implements `complete(messages, tools, max_tokens, *, timeout=None) -> Reply`, where `timeout` caps the remaining call time. The Chat Completions adapter keeps a string `reasoning_content` returned by the peer for later calls; provider compatibility must be confirmed by real integration. Session traces may contain private code, requirements or model output — never publish the whole database.

Test subprocesses and independent acceptance use an environment allowlist. `run` and `resume` accept `--pass-env NAME` for explicit process variables and warn for sensitive names. Workspace tools filter common private key and credential filenames.

Five consecutive tool calls with identical arguments and results end the session with state `stalled` and CLI exit code 2. Use `trace` to view earlier warnings.

## Independent evaluation

Run the 12 basic multi-file cases (`full`) or the 3 eleven-file multi-module backend cases (`multi`) to check that each initial defect fails and the reference fix passes:

```powershell
python -m codeharness.benchmark --mode fixtures --suite full
python -m codeharness.benchmark --mode fixtures --suite multi
```

The first 5 (`core`) cover cart discounts, pagination, inventory, config merging and Decimal invoices; `full` adds date reports, CSV import, order de-duplication, backoff calculation, product search, shipping and metrics. `multi` provides 3 eleven-file backend cases (order pipeline, multi-tenant RBAC gateway, idempotent ledger reconciliation), each requiring a coordinated fix across 3 modules. These are reproducible business fixtures, not issues collected from real open-source projects.

Every case runs the same independent acceptance in a fresh workspace; the acceptance script is not inside that workspace. The initial version must fail on a requirement assertion, then the reference fix or a real agent is verified independently. Reports include run status, independent `success`, request count, tokens, duration and budget skips, saved as `.codeharness/benchmarks/<id>/report.json`. Databases and case workspaces stay in the report directory for traceability.

### Real models and ablation

Only in an environment with a configured `.env`, explicit consent to run test code locally, and an agreed call budget.

Start with a fixed model and only `discount` to confirm native tool calling, independent acceptance and budget behaviour, then expand to the 5 core tasks. The current preferred model is `glm-5.3`:

```powershell
python -m codeharness.benchmark --mode model --task discount --model glm-5.3 --env-file .env --allow-exec --total-requests 12 --total-tokens 24000
```

`.env` holds an authorised model configuration: `CODEHARNESS_BASE_URL`, `CODEHARNESS_API_KEY` and optional `CODEHARNESS_MODEL`. If no URL is given on the command line or via CodeHarness/OpenAI variables, `DASHSCOPE_BASE_URL` and `DASHSCOPE_API_KEY` are read as a pair, with `--model` selecting the model. Credentials stay in local configuration. `--task` and `--suite` are mutually exclusive. The report's `diagnostics` include model errors, retries, tool errors and failed verifications, with tool errors grouped by tool name.

```powershell
python -m codeharness.benchmark --mode model --suite core --env-file .env --allow-exec --total-requests 60 --total-tokens 120000
```

To compare delegation on and off, each task uses its own workspace, the same model and the same per-case limits (default 12 requests, 24,000 tokens, 180 seconds):

```powershell
python -m codeharness.benchmark --mode model --suite core --variants both --env-file .env --allow-exec --total-requests 120 --total-tokens 240000
```

A pair is recorded as `skipped` when the total budget cannot start it. Actual provider billing may exceed the runtime's estimated budget. Explicit authentication or access denial stops the remaining cases. Compare success rate, tokens and duration only over complete pairs, and account for model non-determinism. `--output-tokens` sets the per-call output cap (default 2048). `--output` names a report directory that must not exist yet; `--suite full` expands to the 12 basic tasks and `--suite multi` runs the 3 multi-module tasks. `diagnostics` also count `delegate_calls` and `compactions`.

Where the endpoint supports it, `--reasoning-effort low` lowers reasoning effort in `run`, `resume` or `benchmark`; reports record an explicitly set value. See the [Model Studio GLM docs](https://help.aliyun.com/zh/model-studio/glm) for `glm-5.3` values.

Benchmark acceptance still executes model-written Python code locally; the independent acceptance directory is not a tamper-proof sandbox. Use only for trusted evaluation tasks.

### Model quota pool

Copy `models.example.json` to `.codeharness/models.json`, then set the quota snapshot time, token balances and expiry dates from your provider. Run `python -m codeharness.model_pool status` to view the balances. Worktrees can share a ledger by passing the same absolute configuration path.

```powershell
python -m codeharness.benchmark --mode model --task discount --model-pool .codeharness/models.json --models deepseek-v4.1-flash,deepseek-v4.1-flash-1017 --env-file .env --allow-exec --total-requests 12 --total-tokens 24000
```

Benchmark pairs run on one model. Quota exhaustion preserves the tokens already used and restarts the pair on another eligible model. `run` and `resume` also accept `--model-pool` and `--models`, and charge each actual request against the session budget. `sessions` shows the starting model, and `model_request` events in `trace` identify the model used for each request.

### Current results and limits

| Item | Result | Notes |
| --- | --- | --- |
| Unit and contract tests | 77/78 passed (1 skipped) | Includes 16 local HTTP/CLI contract tests and 4-stage process crash injection; the symlink test is skipped for lack of local permission |
| Reference fixture acceptance | 15/15 passed | `full` 12 + `multi` 3: every initial version fails its assertions and every reference fix passes (0 model calls) |
| `glm-5.3` (`core`, `low`, 4096) | 4/5 (original prompt); `invoice` 1/1 after clarification | 33 requests, 65,570 tokens, 65.82 s, 0 model errors; acceptance exposed a negative-rounding difference under the original prompt |
| `glm-5.3` (`multi`, `low`, 4096) | 3/3 passed | All three 11-file backend tasks fixed across exactly 3 modules; 22 requests, 62,579 tokens, 53.41 s, 0 model errors; `write_file` misuse errors dropped from 3 to 0 |
| Delegation observation | `delegate_calls = 0` | Context stayed below the threshold in these cases and the model read files directly; delegation benefit still needs measuring on larger repositories |

Each case was run once (n = 1), so differences between configurations are not statistically meaningful yet. The deterministic demo (8 calls with delegation, 5 without) fixes the discount and passes tests in both modes; it validates the execution path, not model capability. See [HANDOFF.md](HANDOFF.md#最新交接单) for detailed records and reproduction commands, and [IMPROVEMENT_PLAN.md](IMPROVEMENT_PLAN.md) for the next iteration.

Use `python -m unittest discover -s tests -v` for a full regression. If local loopback connections are forbidden, set `$env:CODEHARNESS_SKIP_LOOPBACK='1'` in PowerShell to explicitly skip the 5 real local HTTP integration tests; simulated transport and CLI tool-chain tests still run. That mode is not a full network regression.

`python -B scripts/regress.py --tag <tag>` runs the unit tests, the `full` and `multi` reference fixtures and the offline demo with and without delegation, writing logs and results to `.codeharness/regress/`; `--compare <summary.json>` diffs against an earlier run and `--skip-loopback` is equivalent to the variable above. CI runs the same script on Ubuntu and Windows with Python 3.11–3.13, without calling any real model.

## Design trade-offs

- The loop is not bound to any provider SDK; model interface, tool permissions, context, event persistence and CLI are explicitly separated.
- SQLite events keep reproducible inputs and execution evidence; file checkpoints detect change and are not automatic transactional rollback.
- Read-only exploration first, then edit and test when needed; task outcomes are judged by independent acceptance. Syntax diagnostics are not functional verification and do not block intermediate edits.
- Lightweight and observable over high concurrency, multi-model orchestration or a GUI; real model data should drive the next optimisation.

Design references: [Pi](https://github.com/earendil-works/pi),
[Claude Code public docs](https://code.claude.com/docs/en/how-claude-code-works),
[DeepSeek Harness](https://github.com/deepseek-ai/deepseek-harness),
[oh-my-pi](https://github.com/can1357/oh-my-pi). This project is an independent Python implementation and copies none of their runtime code.

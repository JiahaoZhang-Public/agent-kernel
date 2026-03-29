# Changelog

## v0.4.2 (2026-03-29)

### Fixed

- **LLM API error handling in AgentLoop** — `litellm.acompletion()` exceptions are now caught and returned as `[LLM error: ...]` strings instead of propagating unhandled to the caller
- **AST structural test upgraded** — `test_execute_tool_call_only_uses_submit` now uses proper `ast.parse()` inspection per v2.2 §6.2 (was source string matching), verifying exactly one `_submit` call and no forbidden execution calls

### Added

- **Structured logging for agent loop** — `AgentLoop.run()` emits structured log messages via `logging.getLogger(__name__)`:
  - `agent_loop.start` — model, max_turns, tool count
  - `agent_loop.tool_calls` — turn number, call count, tool names
  - `agent_loop.done` — model, turns used
  - `agent_loop.llm_error` — model, turn, error details (ERROR level)
  - `agent_loop.max_turns` — warning when limit reached
  - `agent_loop.unexpected_finish` — warning for non-stop finish reasons
- **`submit` parameter on `run_agent_loop()`** — convenience API now supports `ReversibleActionLayer` integration without requiring manual `AgentLoop` construction
- **ReversibleActionLayer integration test** — `test_agent_loop_with_reversible_layer` wires `AgentLoop` with real `ReversibleActionLayer.submit` override, completing v2.2 §8.4 test coverage
- **4 new agent loop tests** — LLM error handling (2), structured logging verification (2)

### Validated

- 187 unit/integration tests passing, 80%+ coverage
- ruff format — passing

## v0.4.1 (2026-03-28)

### Fixed

- **Best-effort error handling in ReversibleActionLayer** — `strategy.capture()` and `store.save()` failures now degrade gracefully per design §7.1-7.2 instead of crashing the submit flow
- **CLAUDE.md stale reference** — removed outdated "OpenAI Agents SDK" requirement, updated to reflect kernel-native agent loop with LiteLLM

### Added

- **`FsDeleteSnapshotStrategy`** — snapshot strategy for `fs.delete` actions; captures file content before deletion, restores via `fs.write` on rollback
- **`SubmitFn` type alias** — `Callable[[ActionRequest], ActionResult]` for clearer submit callable contracts
- **v2.2 design document** — formal specification for `AgentLoop` and `ToolDef` at `docs/research/design/v2.2/Kernel_Design_v2.2.md`
- **5 failure injection tests** — per design §10.6: capture failure, save failure, nonexistent rollback, policy-denied restore, concurrent modification
- **2 FsDeleteSnapshotStrategy integration tests** — rollback after delete, delete nonexistent file
- **Reversible layer components exported** — `ReversibleActionLayer`, `SnapshotStrategy`, `SnapshotStore`, `FsWriteSnapshotStrategy`, `FsDeleteSnapshotStrategy`, `SubmitFn` added to package `__all__`

### Changed

- **SnapshotStore JSON schema** aligned with v2.1 design: `original_request` key (was `request`), ISO 8601 `created_at` (was float), `expires_at` field added. Backward-compatible loading of legacy format.
- **record_id log gap documented** — `Record.record_id` and `ActionResult.record_id` docstrings clarify that log-to-snapshot correlation is caller-side only (kernel unchanged per v2.1 principle)

### Validated

- 204 unit/integration tests passing, 96% coverage
- ruff lint, ruff format, mypy strict — all passing

## v0.4.0 (2026-03-27)

### Breaking Changes

- **Replaced OpenAI Agents SDK with kernel-native agent loop** — `@kernel_tool`, `create_kernel_agent()`, and `run_agent()` are removed. Use `ToolDef` + `AgentLoop` instead. See migration guide in `docs/research/plans/2026-03-27-kernel-native-agent-loop.md`.
- **Dependency change** — `openai-agents>=0.13` replaced with `litellm>=1.40`

### Added

- **`AgentLoop`** — kernel-native agent loop where `kernel.submit()` is the **sole execution path**. No wrapper, no decorator, no opt-in. Structural enforcement of "all access through Gate" invariant.
- **`ToolDef`** — declarative tool definitions containing only metadata (name, description, parameters, action, target mapping). Zero execution logic.
- **`run_agent_loop()`** — convenience function for one-shot agent execution
- **LiteLLM integration** — supports 100+ LLM providers (OpenAI, Anthropic, Ollama, etc.) via unified `litellm.acompletion()` interface
- **Gate enforcement structural test** — AST-based verification that `AgentLoop._execute_tool_call` contains only `kernel.submit()` as execution path
- **`submit` callable override** — `AgentLoop` accepts optional `submit` parameter for `ReversibleActionLayer` integration

### Changed

- **`agent_loop.py`** — complete rewrite from OpenAI Agents SDK wrapper to kernel-native implementation
- **`__init__.py`** — exports updated: `AgentLoop`, `ToolDef`, `run_agent_loop` replace old SDK wrappers

### Validated

- 207 unit/integration tests passing, 96%+ coverage
- 5 live E2E tests passing (gpt-5.4-mini)
- All 15 real MCP integration tests passing
- All core kernel tests unchanged and passing

## v0.3.0 (2026-03-27)

### Added

- **Live E2E OpenAI API Tests** (`tests/test_e2e_openai.py`) — 5 tests validating the full agent-kernel workflow against a real LLM:
  - Agent reads file through kernel-gated `kernel_tool`
  - Policy blocks unauthorized writes (DENIED logged)
  - Multi-tool read → write workflow
  - Invariant: every LLM tool call produces a log entry
  - Process exec tool through kernel
- **Real MCP Server Integration Tests** (`tests/test_mcp_real.py`) — 15 tests using a self-contained Python stdio MCP server (no external deps):
  - `McpClient` connect/initialize, `tools/list`, `tools/call` (echo, add)
  - Error propagation (`isError=True`, unknown tool, JSON-RPC errors)
  - Multiple calls on same connection, close/reconnect
  - `McpProvider` through Kernel Gate with policy enforcement
- **Performance & Load Benchmarks** (`scripts/perf_test.py`) — 6 benchmarks with ops/sec and p50/p95/p99 latency reporting:
  - Sequential throughput: 77,048 ops/s (deny-only), 29,526 ops/s (fs.read with provider)
  - Concurrent load: 10 threads × 100 ops with log integrity verification
  - Mixed allow/deny stress: 1,000 ops with correctness assertion
  - Write throughput: 200 file creates
- **Full E2E Demo Script** (`scripts/e2e_agent_demo.py`) — end-to-end walkthrough:
  - Agent reads CSV sales data and writes analysis report
  - Simulates accidental overwrite + reversible layer rollback
  - Prints full audit log summary

### Fixed

- **`test_agent_denied_write_outside_policy`**: test was prompting agent to write to `/etc/passwd` which triggered LLM safety refusal without calling the tool; switched to an in-workspace but policy-excluded path and asserts on the kernel log (the authoritative invariant) rather than LLM text
- **`test_agent_exec_process_tool`**: `args: list` produced JSON schema without `items`, rejected by OpenAI API with 400; changed to `args: list[str] | None = None`
- **Assertion normalization**: handle space-separated output from LLM echo responses

### Validated on Real Server (GPU server, RTX 4090)

- All 5 live OpenAI API tests pass (model: gpt-5.4-mini)
- All 15 real MCP server integration tests pass
- All 6 performance benchmarks complete with zero errors
- Full E2E demo runs end-to-end: agent writes report, rollback restores file, audit log complete

## v0.2.0 (2026-03-27)

### Added

- **MCP Provider** — full implementation replacing the v0.1.0 stub
  - `McpClient` — JSON-RPC 2.0 client over stdio transport
  - MCP initialize/initialized handshake
  - `tools/call` and `tools/list` support
  - Lazy client connection (connects on first use per server)
  - Configurable server commands and environment variables
- **CLI Entry Point** — `python -m agent_os_kernel` with subcommands:
  - `submit` — execute a single action through the kernel
  - `log` — display and filter kernel log entries
  - `validate-policy` — validate a YAML policy file
  - `version` — print version information
- **Example Configs** — three ready-to-use policy templates:
  - `configs/example_policy.yaml` — balanced read/write with restricted network
  - `configs/restrictive_policy.yaml` — read-only filesystem, no network
  - `configs/permissive_policy.yaml` — broad access for trusted environments
- **Demo Script** — `scripts/demo_kernel.py` showing complete kernel usage
- **API Reference Documentation** — auto-generated from docstrings
- **User Guides** — policy configuration, custom providers, MCP integration
- **End-to-end Integration Tests** — full kernel workflow tests
  - Filesystem CRUD cycle through kernel
  - Policy enforcement across multiple providers
  - Reversible layer write-and-rollback
  - Log integrity and timestamp ordering

### Changed

- **`kernel_tool` wrapper** — fixed function signature to match OpenAI Agents SDK's
  `on_invoke_tool(ctx, args_json_string)` contract (was incorrectly using `**kwargs`)

### Improved

- **Test Coverage** — 185+ tests, 96%+ coverage (up from 133 tests, 89%)
  - Added tests for `config.py` (was 0%, now 100%)
  - Added tests for `agent_loop.py` wrapper paths (was 67%, now 95%)
  - Added comprehensive MCP provider tests with mocked subprocess
  - Added CLI tests for all commands
  - Added e2e integration tests for full workflows

## v0.1.0 (2026-03-27)

### Added

- **Core Kernel** — `Kernel` class with single API `submit(ActionRequest) -> ActionResult`
  - Policy-based authorization (YAML allow-list, glob matching, default deny)
  - Append-only JSONL audit log (every decision produces exactly one record)
  - Provider registry for action dispatch
- **Object Model** — `ActionRequest`, `ActionResult`, `Record` dataclasses
- **Policy Engine** — YAML policy loading with glob-based resource matching and constraint support
- **Built-in Providers**
  - `FilesystemProvider` — `fs.read`, `fs.write`, `fs.delete`
  - `ProcessProvider` — `proc.exec`
  - `HttpProvider` — `net.http` (GET, POST, etc. via urllib)
  - `McpProvider` — `mcp.call` (stub, pending MCP client integration)
- **Reversible Action Layer (v2.1)** — optional layer for snapshot-based rollback
  - `SnapshotStrategy` ABC for action-type-specific snapshots
  - `FsWriteSnapshotStrategy` for filesystem write rollback
  - `SnapshotStore` with TTL-based expiration
  - `ReversibleActionLayer` coordinating capture, execution, and rollback
- **OpenAI Agents SDK Integration** — `@kernel_tool` decorator and `create_kernel_agent()` helper
- **Comprehensive test suite** — 124 tests, 93% coverage
- Initial project scaffold with CI, pre-commit hooks, and MkDocs documentation setup

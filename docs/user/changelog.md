# Changelog

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

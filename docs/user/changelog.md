# Changelog

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

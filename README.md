# Agent OS Kernel

[![CI](https://github.com/JiahaoZhang-Public/agent-kernel/actions/workflows/ci.yml/badge.svg)](https://github.com/JiahaoZhang-Public/agent-kernel/actions/workflows/ci.yml)
[![Coverage](https://img.shields.io/badge/coverage-96%25-brightgreen)](https://github.com/JiahaoZhang-Public/agent-kernel)
[![PyPI](https://img.shields.io/badge/version-0.4.0-blue)](https://github.com/JiahaoZhang-Public/agent-kernel/releases)
[![Python](https://img.shields.io/badge/python-3.10%2B-blue)](https://www.python.org/)
[![License: MIT](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**A security boundary for LLM agents.** Every action an agent takes — read, write, execute, HTTP call, MCP tool — is authorized by policy, logged immutably, and optionally reversible. By the kernel. Not by the agent itself.

---

## Why

When you give an LLM access to tools, nothing enforces what it can actually do. The agent may misread instructions, be manipulated by prompt injection, or simply make a mistake — and there is no layer between it and the real world.

Agent OS Kernel sits between your agent and the world:

```
Agent (LLM)
    │ tool calls
    ▼
┌─────────────────────────────────────────────┐
│              Agent OS Kernel                │
│                                             │
│   Policy ──► Gate ──► Provider ──► World   │
│               │                            │
│              Log (append-only JSONL)        │
└─────────────────────────────────────────────┘
```

**One API. Three components. Three invariants.**

| Invariant | Meaning |
|---|---|
| All access through Gate | Agents cannot touch the world except via `submit()` |
| Default deny | Actions not explicitly allowed are blocked |
| No silent actions | Every decision — allowed or denied — produces exactly one log record |

---

## Features

- **Policy-based authorization** — YAML allow-list with glob resource matching and extensible constraint support
- **Append-only audit log** — tamper-evident JSONL; every `submit()` call is recorded with status, duration, and error
- **Reversible Action Layer** — snapshot-and-rollback for write operations; safety net between "permitted" and "intended"
- **Pluggable providers** — filesystem, process, HTTP, MCP (Model Context Protocol) out of the box
- **Kernel-native agent loop** — `AgentLoop` + `ToolDef` with `kernel.submit()` as the sole execution path; LiteLLM for 100+ LLM providers
- **CLI** — `python -m agent_os_kernel submit | log | validate-policy | version`
- **High throughput** — 77,000+ ops/s, p99 < 0.1 ms (measured on real hardware)

---

## Quick Start

```bash
pip install agent-os-kernel
```

```python
from agent_os_kernel import Kernel, ActionRequest
from agent_os_kernel.policy import Policy, CapabilityRule
from agent_os_kernel.providers.filesystem import FilesystemProvider

policy = Policy(capabilities=[
    CapabilityRule(action="fs.read",  resource="/workspace/**"),
    CapabilityRule(action="fs.write", resource="/workspace/output/**"),
])

with Kernel(policy=policy, providers=[FilesystemProvider()], log_path="kernel.log") as kernel:
    result = kernel.submit(ActionRequest(action="fs.read", target="/workspace/data.csv"))
    print(result.status)   # OK

    denied = kernel.submit(ActionRequest(action="fs.read", target="/etc/passwd"))
    print(denied.status)   # DENIED
```

---

## Agent Loop

`AgentLoop` makes `kernel.submit()` the **sole execution path** — no decorator, no wrapper, no opt-in. Tool definitions are pure metadata (`ToolDef`); they contain no execution logic.

```python
import asyncio
from agent_os_kernel import Kernel, AgentLoop, ToolDef

read_file = ToolDef(
    name="read_file",
    description="Read a file",
    parameters={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
    action="fs.read",
    target_from="path",
)

write_file = ToolDef(
    name="write_file",
    description="Write a file",
    parameters={"type": "object", "properties": {"path": {"type": "string"}, "content": {"type": "string"}}, "required": ["path", "content"]},
    action="fs.write",
    target_from="path",
)

loop = AgentLoop(
    kernel=kernel,
    model="gpt-4o",  # or "anthropic/claude-sonnet-4-20250514", "ollama/llama3", etc.
    instructions="You are a data analyst. Read CSVs and write reports.",
    tools=[read_file, write_file],
)

result = asyncio.run(loop.run("Read /workspace/sales.csv and write a summary to /workspace/output/report.txt"))
```

Every tool call routes through `kernel.submit()` — authorized, logged, and bounded by policy. There is no code path that bypasses the Gate.

---

## Reversible Actions

The Reversible Action Layer wraps the kernel without modifying it. Rollback requests go through the kernel Gate like any other action — they are authorized and logged too.

```python
from agent_os_kernel.reversible import ReversibleActionLayer, SnapshotStore, FsWriteSnapshotStrategy

store = SnapshotStore("/tmp/.snapshots")
layer = ReversibleActionLayer(
    kernel=kernel,
    strategies=[FsWriteSnapshotStrategy()],
    store=store,
)

# Agent writes a file — snapshot captured automatically
result = layer.submit(ActionRequest(action="fs.write", target="/workspace/output/report.txt",
                                    params={"content": "oops, wrong content"}))

# Roll it back
rollback = layer.rollback(result.record_id)
print(rollback.status)  # OK — file restored
```

> Policy bounds the *scope* of damage. Rollback bounds the *duration*.

---

## Providers

| Provider | Actions | Description |
|---|---|---|
| `FilesystemProvider` | `fs.read`, `fs.write`, `fs.delete` | Local filesystem operations |
| `ProcessProvider` | `proc.exec` | Shell command execution |
| `HttpProvider` | `net.http` | GET/POST/PUT/DELETE via urllib |
| `McpProvider` | `mcp.call` | Any MCP server over stdio (JSON-RPC 2.0) |

### MCP Integration

```python
from agent_os_kernel.providers.mcp import McpProvider

provider = McpProvider(servers={
    "my_server": {"command": ["python", "my_mcp_server.py"]},
})

result = kernel.submit(ActionRequest(
    action="mcp.call",
    target="my_server/some_tool",
    params={"arguments": {"key": "value"}},
))
```

---

## Policy Reference

```yaml
# configs/example_policy.yaml
capabilities:
  - action: fs.read
    resource: /workspace/**

  - action: fs.write
    resource: /workspace/output/**

  - action: net.http
    resource: https://api.example.com/**

  - action: mcp.call
    resource: my_server/**
```

```bash
# Validate a policy file
python -m agent_os_kernel validate-policy --policy configs/example_policy.yaml
```

---

## CLI

```bash
# Submit a single action
python -m agent_os_kernel submit --action fs.read --target /workspace/data.csv --policy policy.yaml

# Inspect the audit log
python -m agent_os_kernel log --log-path kernel.log --status DENIED

# Print version
python -m agent_os_kernel version
```

---

## Performance

Measured on `gpuhub-root-rtx4090-48` (Python 3.10):

| Benchmark | Throughput | p99 Latency |
|---|---|---|
| Sequential (deny-only, 2000 ops) | **77,048 ops/s** | 0.02 ms |
| Sequential with fs.read (500 ops) | **29,526 ops/s** | 0.04 ms |
| Concurrent (10 threads × 100 ops) | **7,092 ops/s** | 3.68 ms |
| Mixed allow/deny stress (1000 ops) | **40,566 ops/s** | 0.04 ms |
| Write throughput (200 files) | **14,136 ops/s** | 0.11 ms |
| Log integrity (8 threads × 50 ops) | ✅ 400/400 entries | — |

```bash
python scripts/perf_test.py
```

---

## Installation

```bash
# With uv (recommended)
uv sync --all-extras
uv run pre-commit install

# With pip
pip install agent-os-kernel
```

---

## Development

```bash
# Run tests
uv run pytest

# Run with coverage
uv run pytest --cov=src/agent_os_kernel

# Lint & format
uv run ruff check src/
uv run ruff format src/

# Serve docs
uv run mkdocs serve -f docs/mkdocs.yml

# Run E2E demo (requires OPENAI_API_KEY)
OPENAI_API_KEY=sk-... OPENAI_BASE_URL=https://api.openai-proxy.org/v1 OPENAI_MODEL=gpt-5.4-mini \
    python scripts/e2e_agent_demo.py

# Run performance benchmarks
python scripts/perf_test.py
```

---

## Project Structure

```
src/agent_os_kernel/
├── kernel.py          # Gate — the single submit() entry point
├── policy.py          # Policy engine — YAML loading, glob matching
├── log.py             # Append-only JSONL audit log
├── models.py          # ActionRequest, ActionResult, Record
├── reversible.py      # Reversible Action Layer (v2.1)
├── agent_loop.py      # Kernel-native agent loop (ToolDef + AgentLoop)
├── config.py          # Config loader
├── __main__.py        # CLI entry point
└── providers/
    ├── filesystem.py  # fs.read / fs.write / fs.delete
    ├── process.py     # proc.exec
    ├── http.py        # net.http
    └── mcp.py         # mcp.call (JSON-RPC 2.0 over stdio)

tests/                 # 185+ tests, 96%+ coverage
scripts/               # perf_test.py, e2e_agent_demo.py, demo_kernel.py
configs/               # example_policy.yaml, restrictive_policy.yaml, permissive_policy.yaml
docs/
├── user/              # Public documentation (MkDocs)
└── research/design/   # v0 → v2.1 design specifications
```

---

## Roadmap

- [x] v0.1 — Core kernel: Gate, Policy, Log, Providers, Reversible Layer
- [x] v0.2 — MCP provider, CLI, 96% test coverage
- [x] v0.3 — Live E2E tests, real MCP integration tests, performance benchmarks
- [x] v0.4 — Kernel-native agent loop (all access through Gate enforced structurally)
- [ ] v0.5 — Budget / rate limiting layer
- [ ] v0.6 — Human-in-the-loop approval gate
- [ ] v1.0 — Stable API, full documentation, production hardening

---

## Design

The kernel design is versioned and documented in `docs/research/design/`:

- [v0](docs/research/design/v0/Kernel_Design_v0.md) — initial concept
- [v1](docs/research/design/v1/Kernel_Design_v1.md) — provider model
- [v2](docs/research/design/v2/Kernel_Design_v2.md) — Gate + Policy + Log invariants
- [v2.1](docs/research/design/v2.1/Kernel_Design_v2.1.md) — Reversible Action Layer *(current)*

---

## License

MIT — see [LICENSE](LICENSE).

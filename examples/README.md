# Agent OS Kernel Examples

Runnable examples demonstrating every major feature of the Agent OS Kernel.

## Prerequisites

```bash
# Install from the project root
uv sync        # or: pip install -e .
```

Python 3.10+ required.

## LLM API Configuration

Examples marked **[LLM]** require an OpenAI-compatible API. Configure via environment variables:

| Variable | Default | Description |
|---|---|---|
| `OPENAI_API_KEY` | *(required)* | API key |
| `OPENAI_BASE_URL` | `https://api.openai.com/v1` | API base URL |
| `OPENAI_MODEL` | `gpt-5.4-mini` | Model identifier |

Non-LLM examples work offline with no configuration.

## Categories

| # | Category | Examples | LLM | Description |
|---|----------|---------|-----|-------------|
| 01 | `basic_kernel/` | 4 | No | Direct `kernel.submit()` usage, status codes, audit log |
| 02 | `policy/` | 4 | No | Inline, YAML, glob matching, constraints |
| 03 | `agent_loop/` | 5 | Yes | LLM-driven agents with ToolDef, denial handling |
| 04 | `reversible/` | 4 | No | Snapshot, rollback, TTL expiry, new file rollback |
| 05 | `providers/` | 4 | No | Filesystem, process, HTTP GET/POST |
| 06 | `multi_provider/` | 2 | Mixed | Provider chaining, agent with all providers |
| 07 | `custom_provider/` | 2 | No | Build your own provider (echo, KV store) |
| 08 | `advanced/` | 4 | Mixed | Callable target_from, agent+reversible, log analysis |

## Running Examples

```bash
# Non-LLM examples (no API key needed)
uv run python examples/01_basic_kernel/hello_kernel.py
uv run python examples/02_policy/glob_matching.py
uv run python examples/04_reversible/write_and_rollback.py
uv run python examples/07_custom_provider/kv_store_provider.py

# LLM examples (uses built-in defaults, or set your own key)
uv run python examples/03_agent_loop/minimal_agent.py
uv run python examples/03_agent_loop/file_analyst.py

# Override LLM settings
OPENAI_API_KEY=sk-your-key OPENAI_MODEL=gpt-4o \
  uv run python examples/03_agent_loop/file_analyst.py
```

## Example Highlights

### 01 - Basic Kernel

- **hello_kernel.py** -- Minimal: create kernel, submit one `fs.read`, print result
- **allowed_vs_denied.py** -- Side-by-side OK vs DENIED comparison
- **all_status_codes.py** -- All four kernel paths: OK, DENIED, NO_PROVIDER, INVALID
- **audit_log_inspection.py** -- Submit actions, then read/print the JSONL audit trail

### 02 - Policy

- **inline_policy.py** -- Define policy in Python with `CapabilityRule` objects
- **yaml_policy.py** -- Load policy from a YAML file
- **glob_matching.py** -- Truth table showing `*`, `**`, extension, and exact matching
- **constraint_policy.py** -- Three-part matching: action + resource + constraint

### 03 - Agent Loop [LLM]

- **minimal_agent.py** -- Simplest AgentLoop: one tool, one prompt
- **file_analyst.py** -- Agent reads CSV, computes stats, writes report
- **multi_tool_agent.py** -- Agent with read + write + delete tools
- **run_agent_loop_convenience.py** -- One-liner `run_agent_loop()` helper
- **agent_denied_action.py** -- Agent gracefully handles policy denial

### 04 - Reversible

- **write_and_rollback.py** -- Overwrite file, then rollback to original
- **delete_and_rollback.py** -- Delete file, then rollback to restore it
- **snapshot_expiry.py** -- TTL expiry: rollback fails after snapshot expires
- **new_file_rollback.py** -- Rollback of a newly created file (generates delete)

### 05 - Providers

- **filesystem_ops.py** -- `fs.read`, `fs.write`, `fs.delete` lifecycle
- **process_exec.py** -- Shell commands via `proc.exec`, policy-controlled
- **http_get.py** -- HTTP GET with query params and custom headers
- **http_post.py** -- HTTP POST with JSON body

### 06 - Multi-Provider

- **fetch_and_save.py** -- HTTP GET -> filesystem write pipeline (no LLM)
- **agent_with_all_providers.py** -- Agent using fs + proc + http tools [LLM]

### 07 - Custom Provider

- **echo_provider.py** -- Minimal custom provider (~15 lines)
- **kv_store_provider.py** -- In-memory key-value store with CRUD operations

### 08 - Advanced

- **custom_target_from.py** -- Callable `target_from` for MCP-style routing
- **agent_with_reversible.py** -- AgentLoop with `submit=layer.submit` [LLM]
- **audit_log_analysis.py** -- Parse JSONL log, compute operational statistics
- **programmatic_policy.py** -- Build policy dynamically from data

## Conventions

- Every example is self-contained and uses `tempfile.TemporaryDirectory()` for isolation
- All kernel usage follows the `with Kernel(...) as kernel:` context manager pattern
- `_common.py` provides shared helpers but is not a hard dependency
- Examples are numbered to suggest a reading order from basic to advanced

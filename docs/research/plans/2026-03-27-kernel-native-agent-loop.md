# Plan: Kernel-Native Agent Loop

**Date:** 2026-03-27
**Status:** Draft
**Target Release:** v0.4.0
**Supersedes:** Current `agent_loop.py` (OpenAI Agents SDK integration)

## 1. Problem Statement

The v2 kernel design establishes three invariants:

1. **All access through Gate** — every world-facing action must pass through `kernel.submit()`
2. **Default deny** — actions are blocked unless explicitly allowed by policy
3. **No silent actions** — every decision produces exactly one log record

The current implementation violates invariant #1 at the architecture level. The `@kernel_tool` decorator is opt-in: developers can create tools that bypass the kernel entirely. There is no mechanism to detect or prevent this. The OpenAI Agents SDK's `Runner` owns the tool execution path, and the kernel is merely a wrapper layered on top.

**Root cause:** We are wrapping an existing execution path instead of owning it. The only way to guarantee "all access through Gate" is to make `kernel.submit()` the sole execution path — not a decorator, not a hook, not a wrapper.

## 2. Solution

Replace the OpenAI Agents SDK agent loop with a kernel-native agent loop where `kernel.submit()` is the only code path that executes tool calls. Use LiteLLM as the LLM routing layer to support 100+ model providers.

### 2.1 Architecture

```
User Prompt
    │
    ▼
AgentLoop
    │
    ▼
LiteLLM.acompletion(model, messages, tools)
    │
    ▼
LLM Response
    │
    ├─ finish_reason == "stop" → return final text
    │
    └─ finish_reason == "tool_calls"
            │
            ▼
        for each tool_call:
            ┌─────────────────────────────────┐
            │  map tool_call → ActionRequest   │
            │  kernel.submit(request)          │  ← THE ONLY PATH
            │  format result → tool message    │
            └─────────────────────────────────┘
            │
            ▼
        append tool results to messages
        loop back to LLM
```

**Key guarantee:** The code that converts LLM tool_calls into execution lives inside `AgentLoop._execute_tool_call()`, and it contains exactly one execution mechanism: `self.kernel.submit(request)`. There is no fallback, no bypass, no alternative path.

### 2.2 What Changes

| Component | Before (v0.3) | After (v0.4) |
|-----------|---------------|--------------|
| Agent loop | `agents.Runner` (OpenAI Agents SDK) | `AgentLoop` (kernel-native) |
| Tool definition | `FunctionTool` + `@kernel_tool` decorator | `ToolDef` (declarative, no execution logic) |
| LLM calls | `agents.Runner.run()` → OpenAI API only | `litellm.acompletion()` → 100+ providers |
| Gate enforcement | Opt-in (decorator) | Structural (only execution path) |
| Dependency | `openai-agents>=0.13` | `litellm>=1.40` |

### 2.3 What Does NOT Change

| Component | Status |
|-----------|--------|
| `kernel.py` (Gate) | Unchanged |
| `policy.py` (Policy engine) | Unchanged |
| `log.py` (Audit log) | Unchanged |
| `models.py` (ActionRequest/ActionResult/Record) | Unchanged |
| `providers/*` (fs/proc/http/mcp) | Unchanged |
| `reversible.py` (Reversible Action Layer) | Unchanged |
| `__main__.py` (CLI) | Minor update (remove SDK references if any) |
| `config.py` | Unchanged |

## 3. Detailed Component Design

### 3.1 `ToolDef` — Declarative Tool Definition

```python
@dataclass
class ToolDef:
    """Declares a tool the LLM can call. Contains NO execution logic.

    Execution is always handled by kernel.submit() → provider.execute().
    ToolDef only provides the metadata the LLM needs to generate tool calls
    and the mapping rules to convert tool calls into ActionRequests.
    """
    name: str                                   # Tool name shown to LLM
    description: str                            # Tool description shown to LLM
    parameters: dict[str, Any]                  # JSON Schema for parameters
    action: str                                 # Kernel action: "fs.read", "mcp.call", etc.
    target_from: str | Callable[[dict], str]    # How to extract target from args
```

**Design principle:** A `ToolDef` is pure data. It describes what a tool does and how to map it to an `ActionRequest`. It does not and cannot execute anything. All execution goes through the kernel.

**Example:**

```python
read_file = ToolDef(
    name="read_file",
    description="Read the contents of a file",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "File path to read"}},
        "required": ["path"],
    },
    action="fs.read",
    target_from="path",
)
```

### 3.2 `AgentLoop` — Kernel-Native Agent Loop

```python
class AgentLoop:
    """LLM agent loop where kernel.submit() is the sole execution path.

    Invariant: there is no code path that executes a tool without going
    through kernel.submit(). This is enforced structurally — ToolDefs
    contain no execution logic, and this class only calls kernel.submit().
    """

    def __init__(
        self,
        kernel: Kernel,
        model: str,
        instructions: str = "",
        tools: list[ToolDef] | None = None,
        max_turns: int = 20,
    ):
        self.kernel = kernel
        self.model = model
        self.instructions = instructions
        self.tools = {t.name: t for t in (tools or [])}
        self.max_turns = max_turns

    async def run(self, prompt: str) -> str:
        """Run the agent loop until completion or max_turns."""
        messages = []
        if self.instructions:
            messages.append({"role": "system", "content": self.instructions})
        messages.append({"role": "user", "content": prompt})

        for _ in range(self.max_turns):
            response = await litellm.acompletion(
                model=self.model,
                messages=messages,
                tools=self._tool_schemas() if self.tools else None,
                tool_choice="auto" if self.tools else None,
            )
            choice = response.choices[0]
            message = choice.message

            # Terminal: LLM produced final text
            if choice.finish_reason == "stop":
                return message.content or ""

            # Tool calls: execute each through kernel
            if message.tool_calls:
                messages.append(message)  # assistant message with tool_calls
                for tc in message.tool_calls:
                    result = self._execute_tool_call(tc)
                    messages.append({
                        "role": "tool",
                        "tool_call_id": tc.id,
                        "content": result,
                    })
                continue

            # Unexpected: no tool calls and not stop
            return message.content or ""

        return "[max turns reached]"

    def _execute_tool_call(self, tool_call) -> str:
        """Convert a tool call to an ActionRequest and submit through kernel.

        THIS IS THE ONLY EXECUTION PATH. There is no else branch,
        no fallback, no direct function call. Every tool call becomes
        a kernel.submit() call.
        """
        func = tool_call.function
        tool_def = self.tools.get(func.name)

        if tool_def is None:
            return json.dumps({"error": f"unknown tool: {func.name}", "status": "ERROR"})

        args = json.loads(func.arguments) if func.arguments else {}

        # Resolve target
        if isinstance(tool_def.target_from, str):
            target = str(args.get(tool_def.target_from, func.name))
        else:
            target = tool_def.target_from(args)

        # Submit through kernel — the ONLY execution path
        request = ActionRequest(action=tool_def.action, target=target, params=args)
        result = self.kernel.submit(request)

        return json.dumps({
            "status": result.status,
            "data": result.data,
            "error": result.error,
        }, default=str)

    def _tool_schemas(self) -> list[dict]:
        """Convert ToolDefs to LiteLLM/OpenAI tool format."""
        return [
            {
                "type": "function",
                "function": {
                    "name": td.name,
                    "description": td.description,
                    "parameters": td.parameters,
                },
            }
            for td in self.tools.values()
        ]
```

### 3.3 LiteLLM Integration

LiteLLM is used purely as an LLM call router. It does not participate in tool execution.

- **Dependency:** `litellm>=1.40`
- **Usage:** `litellm.acompletion(model, messages, tools)` — async chat completion
- **Model string format:**
  - OpenAI: `"gpt-4o"`, `"gpt-5.4-mini"`
  - Anthropic: `"anthropic/claude-sonnet-4-20250514"`
  - Local/Ollama: `"ollama/llama3"`
  - Via proxy: set `OPENAI_API_BASE` / `OPENAI_API_KEY` env vars
- **No litellm-specific tool handling:** We use standard OpenAI tool calling format. LiteLLM translates for non-OpenAI providers.

### 3.4 Reversible Action Layer Compatibility

The `ReversibleActionLayer` wraps `kernel.submit()`. To support this, `AgentLoop` accepts an optional `submit` callable that overrides the default `kernel.submit()`:

```python
class AgentLoop:
    def __init__(
        self,
        kernel: Kernel,
        model: str,
        instructions: str = "",
        tools: list[ToolDef] | None = None,
        max_turns: int = 20,
        submit: Callable[[ActionRequest], ActionResult] | None = None,
    ):
        self.kernel = kernel
        self._submit = submit or kernel.submit  # default: kernel.submit
        ...

    def _execute_tool_call(self, tool_call) -> str:
        ...
        result = self._submit(request)  # uses override if provided
        ...
```

Usage:

```python
# Without reversible layer
loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[...])

# With reversible layer
layer = ReversibleActionLayer(kernel, strategies=[...], store=store)
loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[...], submit=layer.submit)
```

The `submit` callable must still go through the kernel internally (as `ReversibleActionLayer.submit()` does). This is not a bypass — it is a composition point. No changes to `ReversibleActionLayer` are needed.

## 4. Files to Change

### 4.1 Modify

| File | Change |
|------|--------|
| `src/agent_os_kernel/agent_loop.py` | **Complete rewrite**: remove all OpenAI Agents SDK code, implement `ToolDef` + `AgentLoop` |
| `src/agent_os_kernel/__init__.py` | Update exports: remove `kernel_tool`, `create_kernel_agent`; add `ToolDef`, `AgentLoop` |
| `pyproject.toml` | Replace `openai-agents>=0.13` with `litellm>=1.40` in dependencies |
| `tests/test_agent_loop.py` | **Complete rewrite**: test `ToolDef`, `AgentLoop`, tool-call-to-ActionRequest mapping, deny behavior |
| `tests/test_e2e_openai.py` | **Rewrite** to use `AgentLoop` + `ToolDef` instead of `@kernel_tool` + `agents.Runner` |
| `scripts/demo_kernel.py` | Update to use new `AgentLoop` API |
| `scripts/e2e_agent_demo.py` | Update to use new `AgentLoop` API |

### 4.2 No Change

| File | Reason |
|------|--------|
| `src/agent_os_kernel/kernel.py` | Gate unchanged |
| `src/agent_os_kernel/policy.py` | Policy engine unchanged |
| `src/agent_os_kernel/log.py` | Audit log unchanged |
| `src/agent_os_kernel/models.py` | Data models unchanged |
| `src/agent_os_kernel/providers/*` | All providers unchanged |
| `src/agent_os_kernel/reversible.py` | Reversible layer unchanged |
| `src/agent_os_kernel/config.py` | Config unchanged |
| `src/agent_os_kernel/__main__.py` | CLI unchanged (no SDK references) |
| `tests/test_kernel.py` | Kernel tests unchanged |
| `tests/test_policy.py` | Policy tests unchanged |
| `tests/test_log.py` | Log tests unchanged |
| `tests/test_models.py` | Model tests unchanged |
| `tests/test_providers.py` | Provider tests unchanged |
| `tests/test_reversible.py` | Reversible tests unchanged |
| `tests/test_mcp.py` | MCP tests unchanged |
| `tests/test_mcp_real.py` | MCP real tests unchanged |
| `tests/test_e2e.py` | Core e2e tests (no agent loop) unchanged |
| `tests/test_cli.py` | CLI tests unchanged |
| `tests/test_config.py` | Config tests unchanged |

## 5. Implementation Steps

### Step 1: Replace dependency (pyproject.toml)

- Remove `openai-agents>=0.13` from `[project].dependencies`
- Add `litellm>=1.40` to `[project].dependencies`
- Run `uv sync` to update lock file

### Step 2: Implement `ToolDef` and `AgentLoop`

Rewrite `src/agent_os_kernel/agent_loop.py`:

1. Define `ToolDef` dataclass (pure metadata, no execution logic)
2. Implement `AgentLoop` class:
   - `__init__`: accept kernel, model, instructions, tools, max_turns
   - `run()`: async method — LLM call loop with tool dispatch
   - `_execute_tool_call()`: the single execution path via `kernel.submit()`
   - `_tool_schemas()`: convert ToolDefs to OpenAI tool format for LiteLLM
3. Add convenience helper `run_agent_loop()` for simple one-shot usage

### Step 3: Update public API

Update `src/agent_os_kernel/__init__.py`:

- Remove: `kernel_tool`, `create_kernel_agent`, `run_agent`
- Add: `ToolDef`, `AgentLoop`

### Step 4: Write unit tests

Rewrite `tests/test_agent_loop.py`:

1. **ToolDef tests:**
   - Schema generation from ToolDef
   - Target resolution (string key vs callable)
   - Tool schema conversion to OpenAI format

2. **AgentLoop tests (mocked LLM):**
   - Tool call → ActionRequest mapping correctness
   - kernel.submit() is called for every tool call
   - DENIED result returned as error string to LLM (not exception)
   - Unknown tool name returns error
   - max_turns limit respected
   - Final text output returned correctly
   - Multiple tool calls in one turn all go through kernel

3. **Gate enforcement tests:**
   - Verify no code path exists that executes without kernel.submit()
   - Verify tool_call with no matching ToolDef returns error (not execution)

### Step 5: Update e2e tests

Rewrite `tests/test_e2e_openai.py`:

- Same 5 test scenarios, same assertions
- Replace `@kernel_tool` + `create_kernel_agent` + `run_agent` with `ToolDef` + `AgentLoop`
- Use `litellm` model string format
- Keep `OPENAI_API_KEY` / `OPENAI_BASE_URL` / `OPENAI_MODEL` env vars

### Step 6: Update demo scripts

Update `scripts/demo_kernel.py` and `scripts/e2e_agent_demo.py`:

- Replace SDK imports with new API
- Demonstrate `ToolDef` + `AgentLoop` usage

### Step 7: Update documentation

- Update `docs/user/getting-started/quickstart.md` (if exists)
- Update `docs/user/guides/` (if exists)
- Update `docs/user/api/` (if exists)
- Update `README.md` usage examples
- Update CHANGELOG.md

### Step 8: Run full test suite

```bash
# Unit + integration tests
pytest tests/ -v

# E2E tests with real LLM (requires API key)
OPENAI_API_KEY=... pytest tests/test_e2e_openai.py -v

# Performance tests
python scripts/perf_test.py
```

### Step 9: Version bump and release

- Bump version to `0.4.0` in `pyproject.toml` and `__init__.py`
- Update CHANGELOG.md with v0.4.0 entry
- Tag `v0.4.0`

## 6. Testing Strategy

### 6.1 Unit Tests (mocked LLM)

Mock `litellm.acompletion` to return controlled responses. Verify:

- Each tool_call triggers exactly one `kernel.submit()` call
- ActionRequest is correctly constructed from tool_call + ToolDef
- DENIED results are formatted as tool response strings
- ERROR results are formatted as tool response strings
- OK results include provider data
- Loop terminates on `finish_reason == "stop"`
- Loop terminates on `max_turns`
- Multiple tool_calls in single response each go through kernel

### 6.2 Integration Tests

Use real kernel with real providers but mocked LLM:

- fs.read through kernel → file content returned
- fs.write through kernel → file created
- proc.exec through kernel → command output returned
- Policy deny → error returned to LLM, file not modified
- All actions produce log records

### 6.3 E2E Tests (real LLM + real kernel)

Reuse existing 5 test scenarios from `test_e2e_openai.py`:

1. Agent reads file through kernel, reports contents
2. Agent write to unauthorized path → DENIED logged
3. Agent read → write workflow
4. Every tool call produces a log entry
5. Agent executes process command through kernel

### 6.4 Gate Enforcement Verification

A dedicated test that verifies the structural guarantee:

```python
def test_no_bypass_path():
    """Verify that ToolDef contains no execution logic
    and AgentLoop only executes via kernel.submit()."""
    import ast, inspect

    # ToolDef should have no callable methods beyond dataclass defaults
    source = inspect.getsource(ToolDef)
    tree = ast.parse(source)
    func_defs = [n for n in ast.walk(tree) if isinstance(n, ast.FunctionDef)]
    assert len(func_defs) == 0, "ToolDef should have no methods"

    # AgentLoop._execute_tool_call should contain exactly one submit call
    source = inspect.getsource(AgentLoop._execute_tool_call)
    assert source.count("kernel.submit") == 1
    assert "subprocess" not in source
    assert "urllib" not in source
```

## 7. Migration Guide

### Before (v0.3)

```python
from agent_os_kernel import Kernel
from agent_os_kernel.agent_loop import kernel_tool, create_kernel_agent, run_agent

kernel = Kernel(policy="policy.yaml", providers=[FilesystemProvider()])

@kernel_tool(kernel, action="fs.read", target_from="path")
def read_file(path: str) -> str:
    """Read a file."""
    return ""

agent = create_kernel_agent(kernel, model="gpt-4o", tools=[read_file])
result = asyncio.run(run_agent(agent, "Read /workspace/data.csv"))
```

### After (v0.4)

```python
from agent_os_kernel import Kernel, ToolDef, AgentLoop

kernel = Kernel(policy="policy.yaml", providers=[FilesystemProvider()])

read_file = ToolDef(
    name="read_file",
    description="Read a file",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string"}},
        "required": ["path"],
    },
    action="fs.read",
    target_from="path",
)

loop = AgentLoop(kernel=kernel, model="gpt-4o", tools=[read_file])
result = asyncio.run(loop.run("Read /workspace/data.csv"))
```

**Key difference:** `read_file` is now pure data (ToolDef). It cannot execute anything. All execution goes through `kernel.submit()` inside `AgentLoop._execute_tool_call()`.

## 8. Risks and Mitigations

| Risk | Mitigation |
|------|------------|
| LiteLLM dependency adds weight | LiteLLM is widely adopted, well-maintained; we use only `acompletion()` |
| LiteLLM tool calling format differences across providers | Test with at least 2 providers (OpenAI, one other); LiteLLM handles translation |
| Losing OpenAI Agents SDK features (guardrails, tracing, handoffs) | Not needed for v0 kernel scope; can be added as layers later |
| Breaking existing users of `@kernel_tool` API | Clear migration guide; major version bump signals breaking change |
| `max_turns` too low for complex tasks | Default 20, configurable per AgentLoop instance |

## 9. Success Criteria

1. `kernel.submit()` is the **only** code path that executes tool calls — verified by structural test
2. All existing e2e test scenarios pass with new implementation
3. Policy deny returns error to LLM, agent continues running
4. Every tool call (allow or deny) produces exactly one log record
5. LiteLLM supports at least OpenAI and OpenAI-compatible proxy endpoints
6. Unit test coverage >= 95% for new `agent_loop.py`
7. No changes to kernel, policy, log, providers, or reversible layer

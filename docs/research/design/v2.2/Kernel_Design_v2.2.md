# Kernel Design v2.2 — Kernel-Native Agent Loop

## Status

This document extends **v2** with a **kernel-native agent loop** — an LLM-driven agent loop where `kernel.submit()` is the sole tool execution path, enforced structurally rather than by convention.

v2.2 answers one question:

> How do we guarantee that ALL agent tool calls go through the Gate, without relying on decorators, hooks, or wrappers that can be bypassed?

## 1. Problem Statement

The v2 design establishes three invariants:

1. **All access through Gate** — every world-facing action must pass through `kernel.submit()`
2. **Default deny** — actions are blocked unless explicitly allowed by policy
3. **No silent actions** — every decision produces exactly one log record

Invariant #1 is an architectural statement. But the v2 design only says "replace `execute` with `kernel.submit`" in §1 — it does not specify how the agent loop itself should be structured.

If the agent loop is owned by an external framework (OpenAI Agents SDK, LangGraph, etc.), the kernel becomes a wrapper layered on top of that framework's execution path. A developer can create tools that bypass the kernel entirely. The invariant is opt-in, not structural.

**Root cause:** Wrapping an existing execution path cannot guarantee the invariant. The only guarantee comes from owning the execution path.

## 2. Solution

Build a kernel-native agent loop where:

1. **`kernel.submit()` is the only code path** that executes tool calls
2. **`ToolDef` is metadata-only** — it contains no execution logic, no function references, no callbacks
3. **LiteLLM** handles LLM routing to 100+ providers without coupling to any specific framework

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

### 2.2 What Changes From v2

| Component | v2 Status | v2.2 Status |
|---|---|---|
| Kernel (Gate, Policy, Log) | Core | **Unchanged** |
| Providers | Pluggable executors | **Unchanged** |
| Reversible Action Layer (v2.1) | Optional wrapper | **Unchanged** |
| Agent loop | "Replace execute with kernel.submit" | **Formalized: AgentLoop class** |
| Tool definitions | Not specified | **Formalized: ToolDef dataclass** |
| LLM integration | Not specified | **LiteLLM routing** |

### 2.3 What Does NOT Change

All v2 properties remain intact:

- One API: `submit(action_request) → action_result`
- Three components: Policy, Gate, Log
- Three invariants: all access through Gate, default deny, no silent actions
- Provider contract: declares actions, executes authorized requests
- ~30 lines of kernel logic

## 3. Component Design

### 3.1 ToolDef

A `ToolDef` declares a tool the LLM can call. It contains **no execution logic**.

```python
@dataclass
class ToolDef:
    name: str                                    # Tool name shown to LLM
    description: str                             # Tool description shown to LLM
    parameters: dict[str, Any]                   # JSON Schema for parameters
    action: str                                  # Kernel action type, e.g. "fs.read"
    target_from: str | Callable[[dict], str]     # How to extract target from args
```

**Key design decision:** `ToolDef` has no `execute` method, no function reference, no callback. It only carries:

- The metadata the LLM needs to generate tool calls (`name`, `description`, `parameters`)
- The mapping rules to convert tool calls into `ActionRequest` objects (`action`, `target_from`)

This separation is the structural guarantee. There is no code path from `ToolDef` to execution — only from `ToolDef` to `ActionRequest`, and from `ActionRequest` through `kernel.submit()`.

#### target_from Resolution

The `target_from` field determines how the `ActionRequest.target` is extracted from the LLM's tool call arguments:

- **String:** Uses that parameter name from the args dict. Example: `target_from="path"` extracts `args["path"]` as the target.
- **Callable:** Calls the function with the args dict. Example: `target_from=lambda args: f"{args['server']}/{args['tool']}"` for MCP targets.
- **Fallback:** If the string key is not found in args, the tool name is used as the target.

### 3.2 AgentLoop

The LLM-driven agent loop. Iterates until the LLM produces a final text response or `max_turns` is reached.

```python
class AgentLoop:
    def __init__(
        self,
        kernel: Kernel,
        model: str,                          # LiteLLM model string
        instructions: str = "",              # System prompt
        tools: list[ToolDef] | None = None,
        max_turns: int = 20,
        submit: SubmitFn | None = None,      # Override for ReversibleActionLayer
    ) -> None: ...

    async def run(self, prompt: str) -> str: ...
```

#### Submit Override

The `submit` parameter allows injecting an alternative submit callable (e.g., `ReversibleActionLayer.submit`) without modifying the kernel or the loop. Default is `kernel.submit()`.

```python
# Without reversible layer
loop = AgentLoop(kernel=k, model="gpt-4o", tools=tools)

# With reversible layer
layer = ReversibleActionLayer(k, strategies, store)
loop = AgentLoop(kernel=k, model="gpt-4o", tools=tools, submit=layer.submit)
```

The `SubmitFn` type alias is defined as:

```python
SubmitFn = Callable[[ActionRequest], ActionResult]
```

### 3.3 Run Loop Algorithm

```python
async def run(self, prompt: str) -> str:
    messages = [system_prompt, user_prompt]

    for _ in range(max_turns):
        response = await litellm.acompletion(model, messages, tools)
        choice = response.choices[0]

        # Terminal: LLM produced final text
        if choice.finish_reason == "stop":
            return choice.message.content

        # Tool calls: execute each through kernel
        if choice.message.tool_calls:
            messages.append(choice.message)
            for tc in choice.message.tool_calls:
                result = self._execute_tool_call(tc)
                messages.append(tool_result_message(tc.id, result))
            continue

        # Unexpected finish reason
        return choice.message.content or ""

    return "[max turns reached]"
```

### 3.4 Tool Call Execution

```python
def _execute_tool_call(self, tool_call) -> str:
    """Convert a tool call to an ActionRequest and submit through kernel.

    THIS IS THE ONLY EXECUTION PATH.
    """
    tool_def = self.tools.get(tool_call.function.name)
    if tool_def is None:
        return json.dumps({"error": "unknown tool", "status": "ERROR"})

    args = json.loads(tool_call.function.arguments)

    # Resolve target from ToolDef mapping
    if isinstance(tool_def.target_from, str):
        target = str(args.get(tool_def.target_from, tool_call.function.name))
    else:
        target = tool_def.target_from(args)

    # Submit through kernel — the ONLY execution path
    request = ActionRequest(action=tool_def.action, target=target, params=args)
    result = self._submit(request)

    return json.dumps({"status": result.status, "data": result.data, "error": result.error})
```

**Structural guarantee:** There is no `else` branch, no fallback, no direct function call. Every tool call becomes a `kernel.submit()` call.

## 4. LLM Integration

### 4.1 Why LiteLLM

| Requirement | LiteLLM | Native SDK |
|---|---|---|
| Multi-provider support | 100+ providers via one API | One provider per SDK |
| OpenAI-compatible tool format | Native | Varies by provider |
| Async support | `acompletion()` | Varies |
| No agent framework coupling | Pure LLM routing | Some SDKs bundle agent logic |
| Dependency footprint | One package | N packages |

LiteLLM is a **routing layer**, not an agent framework. It translates model strings like `"gpt-4o"`, `"anthropic/claude-sonnet-4-20250514"`, `"ollama/llama2"` into the correct API calls. It does not own tool execution, manage state, or impose a loop structure.

### 4.2 Model String Convention

LiteLLM model strings follow the format `provider/model_name`:

```python
AgentLoop(kernel=k, model="gpt-4o", ...)             # OpenAI
AgentLoop(kernel=k, model="anthropic/claude-sonnet-4-20250514", ...)  # Anthropic
AgentLoop(kernel=k, model="ollama/llama2", ...)       # Local Ollama
AgentLoop(kernel=k, model="azure/gpt-4", ...)         # Azure OpenAI
```

## 5. Data Flow

### 5.1 Complete Tool Call Data Flow

```
LLM generates tool_call:
  function.name = "read_file"
  function.arguments = '{"path": "/workspace/data.csv"}'
    │
    ▼
AgentLoop._execute_tool_call():
  1. Lookup ToolDef by name → ToolDef(action="fs.read", target_from="path")
  2. Parse arguments → {"path": "/workspace/data.csv"}
  3. Resolve target → "/workspace/data.csv" (from args["path"])
  4. Build ActionRequest(action="fs.read", target="/workspace/data.csv", params={...})
    │
    ▼
self._submit(request):  [kernel.submit or layer.submit]
  → Gate: validate → authorize → dispatch → log
  → Provider: FilesystemProvider.execute()
  → Result: ActionResult(status="OK", data="file content...")
    │
    ▼
Format result as JSON string → append to messages as tool response
```

### 5.2 Integration with v2.1 Reversible Layer

```
AgentLoop
    │
    ▼ (submit override)
ReversibleActionLayer.submit()
    ├── Capture snapshot (if strategy exists)
    │
    ▼
Kernel.submit()
    ├── Gate: validate → authorize → dispatch → log
    │
    ▼
Provider.execute()
    │
    ▼ (return path)
ReversibleActionLayer
    ├── Persist snapshot (if OK)
    │
    ▼
AgentLoop
    ├── Format result for LLM
```

## 6. Security Properties

### 6.1 Structural Guarantee

The invariant "all access through Gate" is guaranteed by construction:

1. `ToolDef` has no execution logic — it cannot be called
2. `AgentLoop._execute_tool_call()` has exactly one execution mechanism: `self._submit()`
3. `self._submit` defaults to `kernel.submit()` or an explicit override (e.g., `layer.submit`)
4. There is no alternate path, no fallback, no bypass

### 6.2 Verification

The guarantee can be verified by AST inspection:

```python
# Verify: _execute_tool_call calls self._submit and nothing else
import ast
tree = ast.parse(inspect.getsource(AgentLoop._execute_tool_call))
calls = [node for node in ast.walk(tree) if isinstance(node, ast.Call)]
submit_calls = [c for c in calls if "submit" in ast.dump(c)]
assert len(submit_calls) == 1  # Exactly one submit call
```

This test exists in the test suite as `test_gate_enforcement_structural`.

### 6.3 Comparison with Framework Integration

| Property | External Framework | Kernel-Native Loop |
|---|---|---|
| Gate enforcement | Opt-in (decorator/wrapper) | Structural |
| Bypass possible? | Yes (register tool without decorator) | No (no execution path exists) |
| Verification | Runtime checks | Static analysis / AST |
| Framework coupling | High (locked to one SDK) | None (LiteLLM is routing only) |

## 7. Convenience API

```python
async def run_agent_loop(
    kernel: Kernel,
    model: str,
    prompt: str,
    *,
    instructions: str = "",
    tools: list[ToolDef] | None = None,
    max_turns: int = 20,
) -> str:
    """Create an AgentLoop and run it. One-liner for simple use cases."""
    loop = AgentLoop(kernel=kernel, model=model, instructions=instructions,
                     tools=tools, max_turns=max_turns)
    return await loop.run(prompt)
```

## 8. Testing Requirements

### 8.1 Unit Tests: ToolDef

```python
def test_tooldef_has_no_execute_method():
    # ToolDef is metadata-only — no callable attribute

def test_tooldef_target_from_string():
    # target_from="path" extracts args["path"]

def test_tooldef_target_from_callable():
    # target_from=lambda args: ... computes target
```

### 8.2 Unit Tests: AgentLoop

```python
def test_execute_tool_call_routes_through_submit():
    # Verify tool call becomes ActionRequest → submit

def test_execute_tool_call_unknown_tool_returns_error():
    # Unknown tool name → error JSON, no submit call

def test_submit_override_is_used():
    # Custom submit callable is called instead of kernel.submit
```

### 8.3 Structural Tests

```python
def test_gate_enforcement_structural():
    # AST inspection: _execute_tool_call has exactly one submit call

def test_tooldef_has_no_callable_attributes():
    # Verify ToolDef fields are data-only
```

### 8.4 Integration Tests

```python
def test_agent_loop_with_mock_llm():
    # Mock LiteLLM → tool_call → kernel.submit → result → final text

def test_agent_loop_max_turns():
    # Verify loop stops after max_turns

def test_agent_loop_with_reversible_layer():
    # Submit override routes through layer.submit
```

### 8.5 End-to-End Tests

```python
def test_agent_loop_real_llm():
    # Real LLM API → real kernel → real providers → verify results
```

## 9. Limitations

### 9.1 Single Agent Only

v2.2 does not address multi-agent orchestration. The loop runs a single agent with sequential tool calls. Multi-agent support (parallel agents, delegation, supervisor patterns) is out of scope.

### 9.2 No Streaming

The current design uses `acompletion()` which returns a complete response. Streaming tool calls (partial arguments arriving incrementally) are not supported in v2.2.

### 9.3 No Memory / State Management

The agent loop does not manage persistent memory or conversation history beyond the current run. Each `run()` call starts fresh. State management (RAG, long-term memory, session persistence) is out of scope.

## 10. Summary

v2.2 formalizes the agent loop that was implied but not specified by v2.

It has **two new components**: `AgentLoop` and `ToolDef`

It has **one type alias**: `SubmitFn`

It preserves **all v2 properties**: the kernel, its invariants, its components, and its ~30 lines of logic are unchanged.

The key contribution is **structural enforcement** of the Gate invariant: by owning the loop and making `ToolDef` metadata-only, there is no code path that bypasses `kernel.submit()`. This is verifiable by static analysis and tested by AST inspection.

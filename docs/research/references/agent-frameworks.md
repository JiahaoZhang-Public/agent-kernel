# Open-Source Agent Frameworks for Kernel Integration

**Date:** 2026-03-27
**Author:** Jiahao Zhang
**Status:** Active survey
**Purpose:** Identify agent frameworks whose loops are simple enough to intercept with `kernel.submit()`, per the v2 kernel design.

## Selection Criteria

The v2 kernel design requires replacing the agent loop's `execute(action)` call with `kernel.submit(action)`. This means we need frameworks where:

1. The agent loop is explicit (observe → think → act), not deeply abstracted behind event systems
2. There is a single, identifiable tool execution point we can hook into
3. The codebase is small enough to understand and modify confidently
4. The project is actively maintained with meaningful community adoption

## Summary Matrix

| Framework | Stars | License | Loop Type | Interception Ease | Recommendation |
|---|---|---|---|---|---|
| OpenAI Agents SDK | ~20k | MIT | Request-response loop | Very easy | **Primary choice** |
| Pydantic AI | ~16k | Apache 2.0 | State machine (graph) | Easy | Strong alternative |
| Google ADK | ~19k | Apache 2.0 | Event stream + callbacks | Easy (hooks) | Strong alternative |
| smolagents | ~26k | Apache 2.0 | Code-based step execution | Easy | Good for code-agent use case |
| Claude Agent SDK | ~6k | MIT + Commercial | Async iterator | Moderate | Built-in MCP, less hackable |
| LangGraph | ~27k | MIT | Graph with distributed nodes | Moderate | Overkill for single agent |
| CrewAI | ~45k | Unknown | Flows + Crews | Moderate | Multi-agent focused |
| AutoGen | ~50k | Unknown | Event-driven actors | Difficult | Not recommended |
| LiteLLM | ~41k | Unknown | N/A (LLM router) | N/A | Useful as LLM layer only |

## Tier 1: Recommended

### OpenAI Agents SDK

- **Repo:** <https://github.com/openai/openai-agents-python>
- **Stars:** ~20.1k | **License:** MIT | **Version:** 0.13.2
- **What it is:** Lightweight framework for single and multi-agent workflows. Successor to OpenAI Swarm. Minimal abstractions by design.

**Agent loop structure.** The `Runner` class in `src/agents/run.py` implements a classic request-response loop: send messages and tool definitions to the LLM, check if the response contains tool calls, execute them, append results, and loop back. The loop terminates on a final output or agent handoff.

```
Runner.run(agent, input):
    while True:
        response = llm.call(messages, tools)
        if response.is_final_output:
            return result
        if response.has_tool_calls:
            results = execute_tools(response.tool_calls)  # <-- intercept here
            messages.append(results)
```

**Tool execution path.** Tool calls are executed in a single place within the run loop. This is the exact pattern our kernel requires: replace `execute_tools()` with calls to `kernel.submit()` for each tool invocation.

**Why it fits.** The framework's philosophy is "very few abstractions." The entire agent loop is readable in one file. The tool execution point is centralized and synchronous within the loop iteration. Integration would require modifying ~50 lines.

**Limitations.** Tied to the OpenAI API format for tool calling. Using non-OpenAI models requires an adapter layer (or LiteLLM).

---

### Pydantic AI

- **Repo:** <https://github.com/pydantic/pydantic-ai>
- **Stars:** ~15.5k | **License:** Apache 2.0 | **Version:** 1.72.0
- **What it is:** Type-safe agent framework built on Pydantic. Supports 25+ model providers. Uses a graph-based state machine internally.

**Agent loop structure.** The loop is a state machine with three nodes: `UserPromptNode` (entry), `ModelRequestNode` (LLM call), and `CallToolsNode` (tool dispatch). The graph transitions between these nodes until reaching `End`.

**Tool execution path.** `CallToolsNode` delegates to `ToolManager.handle_call()`, which validates arguments via Pydantic's `SchemaValidator` and then invokes the tool function. The `ToolManager._call_tool()` method is the single execution point.

```
CallToolsNode.run():
    for tool_call in response.tool_calls:
        result = tool_manager.handle_call(tool_call)  # <-- intercept here
    transition → ModelRequestNode (with results)
```

**Why it fits.** The `ToolManager` is a clean, single interception point. Pydantic's type validation runs before execution, which complements the kernel's own validation step. The framework also has a built-in `requires_approval=True` flag on tools, which maps conceptually to the kernel's policy-based authorization.

**Limitations.** The state machine model is more abstract than a plain while loop. Understanding the full flow requires reading the pydantic-graph internals. Slightly more work to intercept than OpenAI SDK.

---

### Google Agent Development Kit (ADK)

- **Repo:** <https://github.com/google/adk-python>
- **Stars:** ~18.6k | **License:** Apache 2.0 | **Version:** 1.21.0
- **What it is:** Code-first agent toolkit from Google. Designed explicitly with extensibility hooks for tool-level interception.

**Agent loop structure.** The `LlmAgent._run_async_impl()` method drives execution. The Runner invokes the agent, which calls the LLM, receives tool call events, executes tools, and feeds results back.

**Tool execution path.** ADK provides a first-class `before_tool_callback` hook that fires before every tool invocation. The callback receives a `ToolContext` with full invocation details and session state. Returning `None` proceeds with execution; returning a value skips execution entirely (acts as a cached/mocked result).

```python
def before_tool_callback(tool_context: ToolContext) -> Optional[Any]:
    # Inspect tool_context.function_call, tool_context.state
    # Return None to proceed, or a value to skip execution
    return kernel.submit(action_request)  # <-- natural hook point
```

**Why it fits.** The callback mechanism is purpose-built for exactly our use case. No source code modification needed; we register a callback that routes through the kernel. This is the cleanest integration path among all surveyed frameworks.

**Limitations.** The framework is larger and more opinionated than OpenAI SDK. The event-driven internals add complexity if we need to debug the flow. Google-ecosystem conventions (Vertex AI, Gemini) are prominent, though not mandatory.

---

### smolagents (Hugging Face)

- **Repo:** <https://github.com/huggingface/smolagents>
- **Stars:** ~26.2k | **License:** Apache 2.0 | **Version:** 1.24.0
- **What it is:** Minimal agent library (~1,000 lines core) where agents write and execute Python code as actions rather than emitting JSON tool calls.

**Agent loop structure.** The `CodeAgent` extends `MultiStepAgent`. Each step calls the LLM, which generates Python code. The code is parsed by `parse_code_blobs()` and executed by `LocalPythonExecutor`, an AST-based interpreter that walks the syntax tree node by node.

```
CodeAgent._step():
    code = llm.generate(prompt + execution_log)
    parsed = parse_code_blobs(code)
    result = python_executor.execute(parsed)  # <-- intercept here
    if FinalAnswerException raised:
        return final_answer
```

**Tool execution path.** The `LocalPythonExecutor` is the single execution point. It interprets the AST with import whitelisting, operation count limits, and state persistence across steps. Sandboxed backends (E2B, Docker, Modal) are also supported.

**Why it fits.** The code-as-action paradigm is unique and powerful for research agents. The executor is a clear interception point. The entire codebase is small enough to fork and modify. The AST interpretation model means every operation is already inspectable, which aligns with the kernel's "no silent actions" invariant.

**Limitations.** The code-execution model is fundamentally different from tool-call models. Intercepting individual tool calls within generated code requires wrapping tool functions rather than intercepting a single dispatch point. Better suited for scenarios where the agent generates analysis code rather than calling external APIs.

---

## Tier 2: Viable but More Complex

### Claude Agent SDK

- **Repo:** <https://github.com/anthropics/claude-agent-sdk-python>
- **Stars:** ~5.7k | **License:** MIT + Anthropic Commercial Terms
- **What it is:** SDK for building agents using Claude. Uses an async iterator pattern with built-in tool dispatch via MCP.

**Agent loop.** The `query(prompt)` function returns an async iterator that yields message blocks (TextBlock, ToolUseBlock, ToolResultBlock). Tool execution is handled internally by the SDK.

**Interception.** Possible through custom MCP server registration, but the tool dispatch is more tightly coupled to the SDK internals. Less straightforward to intercept than OpenAI SDK or Google ADK's callbacks.

**When to use.** If the project commits to Claude as the sole LLM backend, this SDK provides the tightest integration. The MCP-based tool model is a natural fit for the kernel's provider abstraction.

---

### LangGraph

- **Repo:** <https://github.com/langchain-ai/langgraph>
- **Stars:** ~27.4k | **License:** MIT
- **What it is:** Graph-based orchestration for building stateful, multi-step agent workflows. Part of the LangChain ecosystem.

**Agent loop.** Agents are nodes in a compiled `StateGraph`. Tool execution happens inside node functions, not in a centralized loop. Conditional edges route between nodes based on state.

**Interception.** No single tool execution point. Each tool-calling node would need to be individually wrapped. The distributed architecture is powerful for complex workflows but makes kernel integration more invasive.

**When to use.** If the project evolves toward multi-agent or complex workflow orchestration. Not recommended for the v2 single-agent kernel.

---

### CrewAI

- **Repo:** <https://github.com/crewAIInc/crewAI>
- **Stars:** ~44.6k | **License:** Unknown

Two-tier architecture (Flows for deterministic control, Crews for autonomous agents). Tool execution is distributed across agents and tasks within Crews. MCP integration available. Production-focused but not minimalist. Interception requires hooking at the Task execution level.

---

## Tier 3: Not Recommended for v2

### AutoGen (Microsoft)

- **Repo:** <https://github.com/microsoft/autogen>
- **Stars:** ~50.4k | **License:** Unknown

Event-driven actor model (v0.4 redesign). AsyncIO-based with message passing. No traditional agent loop to intercept. The architecture is designed for distributed multi-agent systems, which is the opposite of our single-agent constraint. High star count reflects enterprise interest, not simplicity.

---

### LiteLLM

- **Repo:** <https://github.com/BerriAI/litellm>
- **Stars:** ~40.8k

Not an agent framework. Unified API gateway for 100+ LLM providers. Useful as a component (drop-in LLM routing under any of the above frameworks) but has no agent loop or tool execution to intercept.

---

## Integration Patterns

Based on the survey, three patterns emerge for integrating `kernel.submit()`:

**Pattern A: Loop replacement (OpenAI SDK, smolagents).** Fork the framework, find the tool execution call in the agent loop, replace it with `kernel.submit()`. Minimal code change, maximum control, but creates a maintenance fork.

```python
# Before
result = execute_tool(tool_call)

# After
request = ActionRequest(action=tool_call.type, target=tool_call.target, params=tool_call.args)
result = kernel.submit(request)
```

**Pattern B: Hook/callback (Google ADK).** Register a callback that intercepts tool execution without modifying framework source code. No fork needed. Cleanest integration, but limited to frameworks that provide hooks.

```python
agent = LlmAgent(
    before_tool_callback=lambda ctx: kernel.submit(to_action_request(ctx))
)
```

**Pattern C: Wrapper/middleware (Pydantic AI, Claude SDK).** Wrap the tool execution layer (ToolManager, MCP server) with a kernel-aware version. Moderate complexity, no fork needed, but tighter coupling to framework internals.

```python
class KernelToolManager(ToolManager):
    def handle_call(self, tool_call):
        request = to_action_request(tool_call)
        result = self.kernel.submit(request)
        return to_tool_result(result)
```

## Recommendation

For the v2 kernel (single agent, open source, naive loop):

1. **Start with OpenAI Agents SDK.** It is the closest match to the v2 design's assumptions. The loop is a literal while loop with a single tool execution point. Integration is ~50 lines of modification. Use LiteLLM underneath if non-OpenAI models are needed.

2. **Keep Google ADK as the alternative.** If the callback-based approach (Pattern B) is preferred over forking, ADK's `before_tool_callback` is purpose-built for this. No source modification required.

3. **Evaluate Pydantic AI if type safety matters.** The `ToolManager` interception aligns well with the kernel's validation step, and Pydantic's argument validation complements the kernel's policy checking.

4. **Use smolagents for code-agent research.** If the agent needs to write and execute analysis code (rather than calling tools via JSON), smolagents' AST-based executor is the right model.

## References

- OpenAI Agents SDK: <https://github.com/openai/openai-agents-python>
- Pydantic AI: <https://github.com/pydantic/pydantic-ai>
- Google ADK: <https://github.com/google/adk-python>
- smolagents: <https://github.com/huggingface/smolagents>
- Claude Agent SDK: <https://github.com/anthropics/claude-agent-sdk-python>
- LangGraph: <https://github.com/langchain-ai/langgraph>
- CrewAI: <https://github.com/crewAIInc/crewAI>
- AutoGen: <https://github.com/microsoft/autogen>
- LiteLLM: <https://github.com/BerriAI/litellm>

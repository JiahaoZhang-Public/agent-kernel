"""OpenAI Agents SDK integration for the Agent OS Kernel.

Per v2 design §1: the kernel replaces `execute(action)` with `kernel.submit(action)`.
This module provides the integration layer between the OpenAI Agents SDK and the kernel.

Integration pattern: wrap each tool function so that calls route through kernel.submit().
The agent sees normal tools, but every invocation passes through the Gate.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from typing import Any

from agents import Agent, FunctionTool, RunConfig, Runner

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest


def kernel_tool(
    kernel: Kernel,
    action: str,
    *,
    name: str | None = None,
    description: str = "",
    target_from: str | Callable[..., str] | None = None,
) -> Callable[[Callable[..., Any]], FunctionTool]:
    """Decorator that wraps a tool function with kernel authorization.

    The decorated function becomes a FunctionTool whose invocations
    pass through kernel.submit() before the original function executes.

    Args:
        kernel: The Kernel instance for authorization.
        action: The action type for this tool, e.g. "mcp.call".
        name: Override the tool name (defaults to function name).
        description: Tool description for the LLM.
        target_from: How to determine the target for the ActionRequest.
            - If a string, uses that parameter name from the tool args.
            - If a callable, calls it with the tool args dict.
            - If None, uses the tool name as the target.

    Returns:
        A decorator that converts a function into a kernel-gated FunctionTool.

    Example:
        @kernel_tool(kernel, action="mcp.call", target_from="query")
        def search_papers(query: str) -> str:
            return mcp_client.call("scholar/search", query=query)
    """

    def decorator(func: Callable[..., Any]) -> FunctionTool:
        tool_name = name or func.__name__
        tool_desc = description or func.__doc__ or ""

        async def wrapper(ctx: Any, args: str) -> str:  # noqa: ARG001
            kwargs: dict[str, Any] = json.loads(args) if args else {}

            # Determine target
            if target_from is None:
                target = tool_name
            elif isinstance(target_from, str):
                target = str(kwargs.get(target_from, tool_name))
            else:
                target = target_from(kwargs)

            # Submit through kernel
            request = ActionRequest(action=action, target=target, params=kwargs)
            result = kernel.submit(request)

            if result.status != "OK":
                return json.dumps({"error": result.error, "status": result.status})

            # If the kernel executed a provider, return that result
            if result.data is not None:
                if isinstance(result.data, str):
                    return result.data
                return json.dumps(result.data)

            # Otherwise, fall through to the original function
            output = func(**kwargs)
            if isinstance(output, str):
                return output
            return json.dumps(output)

        # Create the FunctionTool with proper schema
        return FunctionTool(
            name=tool_name,
            description=tool_desc,
            params_json_schema=_extract_schema(func),
            on_invoke_tool=wrapper,
        )

    return decorator


def create_kernel_agent(
    kernel: Kernel,
    *,
    name: str = "KernelAgent",
    instructions: str = "",
    model: str = "gpt-4o",
    tools: list[FunctionTool] | None = None,
) -> Agent[Any]:
    """Create an Agent wired to the kernel.

    All tools provided should be created with @kernel_tool or manually
    wrapped to route through kernel.submit().

    Args:
        kernel: The Kernel instance.
        name: Agent name.
        instructions: System instructions for the agent.
        model: Model identifier.
        tools: List of kernel-wrapped FunctionTools.

    Returns:
        An Agent instance ready to run.
    """
    return Agent(
        name=name,
        instructions=instructions,
        model=model,
        tools=list(tools) if tools else [],
    )


async def run_agent(
    agent: Agent[Any],
    prompt: str,
    *,
    model: str | None = None,
) -> str:
    """Run an agent with a prompt and return the final output.

    Args:
        agent: The Agent to run.
        prompt: User input prompt.
        model: Optional model override.

    Returns:
        The agent's final text output.
    """
    config = RunConfig(model=model) if model else RunConfig()
    result = await Runner.run(agent, input=prompt, run_config=config)
    return str(result.final_output)


def _extract_schema(func: Callable[..., Any]) -> dict[str, Any]:
    """Extract a JSON schema from function type hints.

    This is a simplified schema extractor for basic types.
    For complex schemas, users should provide params_json_schema directly.
    """
    import inspect
    import typing

    sig = inspect.signature(func)
    hints = typing.get_type_hints(func)
    properties: dict[str, Any] = {}
    required: list[str] = []

    type_map = {
        str: "string",
        int: "integer",
        float: "number",
        bool: "boolean",
        list: "array",
        dict: "object",
    }

    for param_name, param in sig.parameters.items():
        if param_name in ("self", "cls", "ctx"):
            continue

        annotation = hints.get(param_name, inspect.Parameter.empty)
        if annotation is inspect.Parameter.empty:
            json_type = "string"
        else:
            origin = getattr(annotation, "__origin__", None)
            json_type = "string" if origin is not None else type_map.get(annotation, "string")

        properties[param_name] = {"type": json_type}

        if param.default is inspect.Parameter.empty:
            required.append(param_name)

    schema: dict[str, Any] = {
        "type": "object",
        "properties": properties,
    }
    if required:
        schema["required"] = required

    return schema

"""Kernel-native agent loop.

Per v2 design invariant #1: ALL access goes through the Gate.
This module owns the agent loop and enforces that kernel.submit() is the
sole tool execution path. ToolDefs are pure metadata — they contain no
execution logic. AgentLoop converts LLM tool calls into ActionRequests
and submits them through the kernel.

LLM calls are routed through LiteLLM, supporting 100+ model providers.
"""

from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass, field
from typing import Any

import litellm

from agent_os_kernel.kernel import Kernel
from agent_os_kernel.models import ActionRequest, SubmitFn


@dataclass
class ToolDef:
    """Declares a tool the LLM can call. Contains NO execution logic.

    Execution is always handled by kernel.submit() -> provider.execute().
    ToolDef only provides the metadata the LLM needs to generate tool calls
    and the mapping rules to convert tool calls into ActionRequests.

    Attributes:
        name: Tool name shown to the LLM.
        description: Tool description shown to the LLM.
        parameters: JSON Schema for tool parameters.
        action: Kernel action type, e.g. "fs.read", "mcp.call".
        target_from: How to extract the target for the ActionRequest.
            If a string, uses that parameter name from the tool args.
            If a callable, calls it with the args dict to produce the target.
    """

    name: str
    description: str
    parameters: dict[str, Any]
    action: str
    target_from: str | Callable[[dict[str, Any]], str] = field(default="target")


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
        submit: SubmitFn | None = None,
    ) -> None:
        """Initialize the agent loop.

        Args:
            kernel: The Kernel instance for authorization and execution.
            model: LiteLLM model string, e.g. "gpt-4o", "anthropic/claude-sonnet-4-20250514".
            instructions: System prompt for the LLM.
            tools: List of ToolDefs available to the agent.
            max_turns: Maximum LLM call iterations before stopping.
            submit: Optional override for the submit callable. Defaults to
                kernel.submit(). Use this for ReversibleActionLayer integration.
        """
        self.kernel = kernel
        self.model = model
        self.instructions = instructions
        self.tools: dict[str, ToolDef] = {t.name: t for t in (tools or [])}
        self.max_turns = max_turns
        self._submit = submit or kernel.submit

    async def run(self, prompt: str) -> str:
        """Run the agent loop until completion or max_turns.

        Args:
            prompt: User input prompt.

        Returns:
            The agent's final text output.
        """
        messages: list[dict[str, Any]] = []
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
                messages.append(message.model_dump())
                for tc in message.tool_calls:
                    result = self._execute_tool_call(tc)
                    messages.append(
                        {
                            "role": "tool",
                            "tool_call_id": tc.id,
                            "content": result,
                        }
                    )
                continue

            # Unexpected finish reason (e.g. length) — return whatever we have
            return message.content or ""

        return "[max turns reached]"

    def _execute_tool_call(self, tool_call: Any) -> str:
        """Convert a tool call to an ActionRequest and submit through kernel.

        THIS IS THE ONLY EXECUTION PATH. There is no else branch,
        no fallback, no direct function call. Every tool call becomes
        a kernel.submit() call.
        """
        func = tool_call.function
        tool_def = self.tools.get(func.name)

        if tool_def is None:
            return json.dumps({"error": f"unknown tool: {func.name}", "status": "ERROR"})

        args: dict[str, Any] = json.loads(func.arguments) if func.arguments else {}

        # Resolve target
        if isinstance(tool_def.target_from, str):
            target = str(args.get(tool_def.target_from, func.name))
        else:
            target = tool_def.target_from(args)

        # Submit through kernel — the ONLY execution path
        request = ActionRequest(action=tool_def.action, target=target, params=args)
        result = self._submit(request)

        return json.dumps(
            {"status": result.status, "data": result.data, "error": result.error},
            default=str,
        )

    def _tool_schemas(self) -> list[dict[str, Any]]:
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


async def run_agent_loop(
    kernel: Kernel,
    model: str,
    prompt: str,
    *,
    instructions: str = "",
    tools: list[ToolDef] | None = None,
    max_turns: int = 20,
) -> str:
    """Convenience function: create an AgentLoop and run it.

    Args:
        kernel: The Kernel instance.
        model: LiteLLM model string.
        prompt: User input prompt.
        instructions: System prompt for the LLM.
        tools: List of ToolDefs.
        max_turns: Maximum LLM call iterations.

    Returns:
        The agent's final text output.
    """
    loop = AgentLoop(
        kernel=kernel,
        model=model,
        instructions=instructions,
        tools=tools,
        max_turns=max_turns,
    )
    return await loop.run(prompt)

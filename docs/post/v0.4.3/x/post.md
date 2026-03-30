# X (Twitter) Post — Agent OS Kernel v0.4.3

**Platform**: X / Twitter
**Language**: English
**Image**: figure.png (1600x900)

---

## Main Post (Thread starter)

We open-sourced Agent OS Kernel — a security kernel for LLM agents.

Every tool call goes through a Gate: policy check -> execute -> audit log. No bypass path. Enforced structurally, not by convention.

~1,600 LOC | 96% coverage | 77K ops/s | MIT

pip install py-agent-kernel

https://github.com/JiahaoZhang-Public/agent-kernel

## Reply 1 (Thread)

Three invariants, structurally guaranteed:

1. All access through Gate — kernel.submit() is the sole path
2. Default deny — not in policy = blocked
3. No silent actions — every decision logged immutably

ToolDef has zero execution logic. No decorator to forget. No bypass in the code.

## Reply 2 (Thread)

100+ LLM providers via LiteLLM (OpenAI, Anthropic, Ollama, Azure...)
4 built-in providers: filesystem, HTTP, MCP, process
Reversible Action Layer for snapshot + rollback
30 runnable examples

Docs: https://agent-kernel.readthedocs.io

Stars, issues, PRs welcome.

#OpenSource #AI #LLMSecurity #AgentSafety

# LinkedIn Post — Agent OS Kernel v0.4.3

**Platform**: LinkedIn
**Language**: English
**Image**: figure.png (1200x627)

---

We just open-sourced Agent OS Kernel — a security kernel for LLM agents.

When you give an AI agent access to tools, nothing stops it from reading the wrong file, calling the wrong API, or executing a destructive command. The model might hallucinate, get prompt-injected, or simply make a mistake.

We built the missing layer between the agent and the real world.

How it works:
Every tool call goes through a Gate — policy check, execute, audit log. No exceptions. No bypass path. Enforced at the architecture level, not by convention.

Three invariants, structurally guaranteed:
- All access through Gate — kernel.submit() is the sole execution path
- Default deny — if it's not in the policy, it's blocked
- No silent actions — every decision is logged immutably

By the numbers:
- ~1,600 lines of core code
- 96%+ test coverage
- 77,000+ ops/s throughput
- 100+ LLM providers via LiteLLM
- 30 runnable examples
- MIT license

The space is heating up — Microsoft shipped agent-os-kernel (v3.0), Cisco launched Agent Runtime SDK at RSA 2026, and AgentSpec just got accepted at ICSE '26. We're taking a different approach: minimal, architecture-driven, developer-first. Small enough to audit the entire codebase in an afternoon.

pip install py-agent-kernel
GitHub: https://github.com/JiahaoZhang-Public/agent-kernel
Docs: https://agent-kernel.readthedocs.io

If you're building with LLM agents and care about safety, give it a look. Stars, issues, and PRs welcome.

#OpenSource #AI #LLMSecurity #AgentSafety #Python

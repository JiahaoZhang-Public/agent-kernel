# Agent OS Kernel

A security boundary for LLM agents. Every tool call an agent makes is authorized by policy, logged immutably, and optionally reversible — enforced at the architecture level, not by convention.

## Overview

Agent OS Kernel sits between your LLM agent and the real world. When an agent calls a tool — reading a file, executing a shell command, making an HTTP request — the kernel intercepts that call, checks it against a YAML policy, executes it through a registered provider, and logs the decision to an append-only audit trail.

Three invariants are enforced structurally:

- **All access through Gate** — `kernel.submit()` is the only code path that executes tools. `ToolDef` contains zero execution logic; there is no decorator to forget and no bypass path.
- **Default deny** — Actions not explicitly allowed in the YAML policy are blocked.
- **No silent actions** — Every decision, whether allowed or denied, produces exactly one log record.

The kernel-native agent loop uses LiteLLM to support 100+ LLM providers (OpenAI, Anthropic, Ollama, Azure, and more) while routing every tool call through the Gate.

## Quick links

- [Installation](getting-started/installation.md)
- [Quickstart](getting-started/quickstart.md)
- [API Reference](api/index.md)
- [Changelog](changelog.md)

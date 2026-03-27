# API Reference

## Core

### Kernel

::: agent_os_kernel.kernel.Kernel

### ActionRequest

::: agent_os_kernel.models.ActionRequest

### ActionResult

::: agent_os_kernel.models.ActionResult

### Record

::: agent_os_kernel.models.Record

## Policy

### Policy

::: agent_os_kernel.policy.Policy

### CapabilityRule

::: agent_os_kernel.policy.CapabilityRule

### load_policy

::: agent_os_kernel.policy.load_policy

## Log

::: agent_os_kernel.log.Log

## Providers

### Provider (Base)

::: agent_os_kernel.providers.base.Provider

### FilesystemProvider

::: agent_os_kernel.providers.filesystem.FilesystemProvider

### ProcessProvider

::: agent_os_kernel.providers.process.ProcessProvider

### HttpProvider

::: agent_os_kernel.providers.http.HttpProvider

### McpProvider

::: agent_os_kernel.providers.mcp.McpProvider

## Reversible Action Layer

### ReversibleActionLayer

::: agent_os_kernel.reversible.ReversibleActionLayer

### SnapshotStrategy

::: agent_os_kernel.reversible.SnapshotStrategy

### FsWriteSnapshotStrategy

::: agent_os_kernel.reversible.FsWriteSnapshotStrategy

### SnapshotStore

::: agent_os_kernel.reversible.SnapshotStore

## Agent Loop

### ToolDef

::: agent_os_kernel.agent_loop.ToolDef

### AgentLoop

::: agent_os_kernel.agent_loop.AgentLoop

### run_agent_loop

::: agent_os_kernel.agent_loop.run_agent_loop

## CLI

The kernel provides a CLI entry point:

```bash
python -m agent_os_kernel <command> [options]
```

### Commands

| Command | Description |
|---|---|
| `submit` | Submit an action through the kernel |
| `log` | Display kernel log entries |
| `validate-policy` | Validate a policy YAML file |
| `version` | Print version information |

### Examples

```bash
# Validate a policy file
python -m agent_os_kernel validate-policy --policy configs/example_policy.yaml

# Submit an action
python -m agent_os_kernel submit --policy policy.yaml --action fs.read --target /workspace/data.txt

# View log entries
python -m agent_os_kernel log --log-path kernel.log --status OK --limit 10

# Print version
python -m agent_os_kernel version
```

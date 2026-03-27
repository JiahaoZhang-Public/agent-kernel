# Quickstart

## Basic Kernel Usage

### 1. Define a Policy

Create a YAML file (`policy.yaml`) that specifies what actions are allowed:

```yaml
capabilities:
  - action: fs.read
    resource: /workspace/**

  - action: fs.write
    resource: /workspace/output/**

  - action: proc.exec
    resource: git

  - action: net.http
    resource: https://api.example.com/**
    constraint:
      method: GET
```

### 2. Create and Use the Kernel

```python
from agent_os_kernel import Kernel, ActionRequest
from agent_os_kernel.providers.filesystem import FilesystemProvider
from agent_os_kernel.providers.process import ProcessProvider

# Initialize kernel with policy and providers
kernel = Kernel(
    policy="policy.yaml",
    providers=[FilesystemProvider(), ProcessProvider()],
    log_path="kernel.log",
)

# Submit an action — this one is allowed
result = kernel.submit(ActionRequest(
    action="fs.read",
    target="/workspace/data.csv",
))
print(result.status)  # "OK"
print(result.data)    # file contents

# Submit an action — this one is denied by policy
result = kernel.submit(ActionRequest(
    action="fs.write",
    target="/etc/passwd",
    params={"content": "hacked"},
))
print(result.status)  # "DENIED"
print(result.error)   # "not permitted"

kernel.close()
```

### 3. Check the Audit Log

Every `submit()` call produces a JSONL log entry:

```bash
cat kernel.log
```

```json
{"timestamp":"2026-03-27T10:00:01Z","action":"fs.read","target":"/workspace/data.csv","status":"OK","duration_ms":2}
{"timestamp":"2026-03-27T10:00:02Z","action":"fs.write","target":"/etc/passwd","status":"DENIED","error":"not permitted"}
```

## Using the Reversible Action Layer

```python
from agent_os_kernel.reversible import (
    FsWriteSnapshotStrategy,
    ReversibleActionLayer,
    SnapshotStore,
)

# Wrap the kernel with the reversible layer
layer = ReversibleActionLayer(
    kernel=kernel,
    strategies=[FsWriteSnapshotStrategy()],
    store=SnapshotStore(".snapshots"),
)

# Write through the layer — snapshot is captured automatically
result = layer.submit(ActionRequest(
    action="fs.write",
    target="/workspace/output/report.md",
    params={"content": "new content"},
))
print(result.record_id)  # e.g. "a1b2c3d4..."

# Roll back if needed
rollback_result = layer.rollback(result.record_id)
print(rollback_result.status)  # "OK" — original content restored
```

## Agent Loop

`AgentLoop` enforces that `kernel.submit()` is the **sole execution path**. `ToolDef` is pure metadata — it contains no execution logic.

```python
import asyncio
from agent_os_kernel import Kernel, AgentLoop, ToolDef
from agent_os_kernel.providers.filesystem import FilesystemProvider

kernel = Kernel(
    policy="policy.yaml",
    providers=[FilesystemProvider()],
)

# Define a tool (pure metadata — no execution logic)
read_file = ToolDef(
    name="read_file",
    description="Read a file from the workspace.",
    parameters={
        "type": "object",
        "properties": {"path": {"type": "string", "description": "File path"}},
        "required": ["path"],
    },
    action="fs.read",
    target_from="path",
)

# Create and run an agent loop
loop = AgentLoop(
    kernel=kernel,
    model="gpt-4o",  # any LiteLLM-supported model
    instructions="You are a helpful assistant with access to workspace files.",
    tools=[read_file],
)

output = asyncio.run(loop.run("Read the file /workspace/data.csv"))
print(output)
```

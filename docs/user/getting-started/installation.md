# Installation

## Prerequisites

- Python >= 3.10
- [uv](https://docs.astral.sh/uv/) package manager

## Setup

```bash
# Clone the repository
git clone https://github.com/JiahaoZhang-Public/agent-kernel.git
cd agent-kernel

# Install all dependencies (including dev, test, docs)
uv sync --all-extras

# Install pre-commit hooks
uv run pre-commit install
```

## Verify

```bash
uv run pytest
```

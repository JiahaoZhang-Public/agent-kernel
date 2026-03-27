# Agent Os Kernel

## Setup

```bash
# Install uv if you haven't: https://docs.astral.sh/uv/
uv sync --all-extras
uv run pre-commit install
```

## Usage

```bash
# Run tests
uv run pytest

# Lint & format
uv run ruff check src/
uv run ruff format src/

# Serve docs
uv run mkdocs serve -f docs/mkdocs.yml
```

## Project Structure

```
src/agent_os_kernel/     Source code
tests/                   Test suite
docs/user/               Public documentation (MkDocs)
docs/research/           Internal research notes
notebooks/               Jupyter notebooks
scripts/                 Training & evaluation scripts
configs/                 Experiment config files (YAML)
```

## License

MIT

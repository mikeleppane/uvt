# pt - Copilot Instructions

## Overview

**pt** is a Python task runner built on `uv` that provides task orchestration, profiles, task inheritance, and PEP 723 support. The codebase prioritizes type safety (mypy strict mode), Pydantic validation, and clean separation of concerns.

## Architecture & Data Flow

### Core Components

- **models.py** → Pydantic schemas with `ConfigDict(extra="forbid")` for strict validation
  - `TaskConfig` with hooks (`before_task`, `after_task`, `after_success`, `after_failure`)
  - `TaskConfig.tags` with `@field_validator` (alphanumeric + hyphens/underscores)
  - Tag helper methods: `get_tasks_by_tag()`, `get_tasks_by_tags()`, `get_all_tags()`
- **config.py** → Config loading, task inheritance resolution, profile/env merging, .env parsing
  - Hook merge rules: override (child wins if set)
  - Tag merge rules: merge, deduplicate, sort alphabetically
- **runner.py** → Task orchestration, hooks execution, condition evaluation, builds `UvCommand` instances
  - `_execute_hook()` / `_execute_hook_async()`: Execute hook scripts
  - Hook environment: `PT_TASK_NAME`, `PT_HOOK_TYPE`, `PT_TASK_EXIT_CODE`
- **executor.py** → Subprocess execution via `uv run`, timeout handling, output capture
- **parallel.py** → Async task execution with `OnFailure` modes (fail-fast/wait/continue) and output modes (buffered/interleaved)
- **graph.py** → DAG construction, topological sort, cycle detection for task dependencies
- **script_meta.py** → PEP 723 inline metadata parser (`# /// script` blocks)
- **cli.py** → Click commands with tag filtering
  - `pt list --tag <tag>`: Filter tasks by tags (AND logic, use `--match-any` for OR)
  - `pt multi --tag <tag>`: Run tasks with specific tags
  - `pt tags`: List all tags with task counts

### Execution Flow

1. **Config Loading**: Discover `pt.toml` or `pyproject.toml` (walking up directory tree)
2. **Task Resolution**: Resolve task inheritance (`extend` field), merge profile/env vars
3. **Graph Building**: Construct DAG from `depends_on`, detect cycles
4. **Dependency Merging**: Merge inline PEP 723 deps with task deps (deduplicate)
5. **Condition Check**: Evaluate platform/env/file conditions before execution
6. **Before Hook**: Execute `before_task` hook if defined (skip task if hook fails)
7. **Command Building**: Create `UvCommand` with dependencies, PYTHONPATH, env vars
8. **Execution**: Run via `uv run` (async for parallel, sync wrapper for CLI)
9. **After Hooks**: Execute `after_success`/`after_failure` based on result, then `after_task` (always)

## Critical Patterns

### Task Inheritance (Key Merge Rules)

Tasks extend parents via `extend` field. **Never replace lists completely**:

```python
# CORRECT merge behavior in config.py:
1. Override (child wins if set):
   - script, cmd, cwd, timeout, python, description
   - condition, condition_script, ignore_errors, parallel
   - before_task, after_task, after_success, after_failure  # Hooks

2. Merge + dedupe lists (parent first):
   - dependencies, pythonpath, depends_on
   - tags (merged, deduplicated, sorted alphabetically)  # Tags

3. Concatenate (order matters):
   - args (parent args + child args)

4. Merge dicts (child overrides parent keys):
   - env (child env vars override parent)
```

Example in [config.py](../src/pt/config.py#L200-L283):
```python
# Override fields
merged_data["before_task"] = child.before_task or parent.before_task

# Merge lists (unique, preserve order)
merged.dependencies = list({*parent_resolved.dependencies, *task.dependencies})
merged.args = parent_resolved.args + task.args  # Parent first!

# Merge tags (deduplicate and sort)
merged_tags = list(set(parent.tags + child.tags))
merged_data["tags"] = sorted(merged_tags)
```

### Profile & Environment Priority

Environment variables merge in this order (later wins):

1. Global `.env` files
2. Global `[env]` section
3. Profile-specific `.env` files
4. Profile-specific `[profiles.X.env]`
5. Task-specific `env` dict

**PYTHONPATH is additive**: Always merge and dedupe paths from global → profile → task. See [config.py](../src/pt/config.py#L300-L330).

### Async/Sync Bridge Pattern

Public APIs are sync, internal execution is async:

```python
# runner.py pattern:
def run_task(self, name: str) -> ExecutionResult:
    return asyncio.run(self._run_task_async(name))

async def _run_task_async(self, name: str) -> ExecutionResult:
    # Actual async implementation
```

Use `asyncio.run()` only at API boundaries, never nested.

### PEP 723 Integration

Scripts can declare dependencies inline. **Always merge** with task dependencies:

```python
# script_meta.py:
script_deps = parse_script_metadata(script_path)
merged = merge_dependencies(task_deps, script_deps)  # Dedupe
```

## Development Workflow

```bash
# Setup (uses uv)
uv sync                           # Install with dev dependencies
source .venv/bin/activate         # Activate venv

# Testing
pytest tests/                     # Run all tests
pytest tests/test_graph.py -v    # Run specific test
pytest -k "inheritance"           # Run matching tests

# Code quality
ruff format src/ tests/           # Format (line length: 100)
ruff check src/ tests/ --fix     # Lint with auto-fix
mypy src/                         # Type check (strict mode)

# Run locally
python -m pt run <task>           # Via module
uv run pt run <task>              # Via uv
```

## Testing Patterns

Use `tmp_path` fixture for file operations, `textwrap.dedent()` for TOML:

```python
def test_task_inheritance(tmp_path: Path) -> None:
    config_content = textwrap.dedent("""
        [tasks.base]
        dependencies = ["pytest"]
        
        [tasks.test]
        extend = "base"
        dependencies = ["pytest-cov"]
    """)
    config_path = tmp_path / "pt.toml"
    config_path.write_text(config_content)
    # Load and assert...
```

For async tests, pytest-asyncio is configured with `asyncio_mode = "auto"`.

## Error Handling

Custom exceptions with user-friendly messages:

- `ConfigError` → Config validation/loading failures
- `ConfigNotFoundError` → No config file found (walks up from cwd)
- `CycleError` → Circular task dependencies
- `UnknownTaskError` → Task not found (could suggest similar names)

Always provide context in errors: file paths, task names, cycle details.

## Rich Output Conventions

- Use `Console` for output, never raw `print()`
- `Table` for task lists (`pt list`)
- `Progress` with `SpinnerColumn` for long operations
- `Panel` for task output in buffered mode
- Respect `--quiet` flag (skip non-essential output)

## Common Gotchas

1. **Import alias inconsistency**: Code uses `pyr` in some places, `pt` in others (legacy rename). Always use `pt` for new code.
2. **Path resolution**: Always use `resolve_path(path, project_root)` from config.py for relative paths.
3. **Environment expansion**: Use `dotenv.py` for `${VAR}` expansion, not manual string replacement.
4. **Dependency deduplication**: Use `list({*deps1, *deps2})` pattern to preserve order while deduping.
5. **Profile names**: `default_profile` in config vs `--profile` CLI arg vs `PT_PROFILE` env var (precedence: CLI → env → config).

## Key Files for Reference

- [models.py](../src/pt/models.py) - All Pydantic schemas, see `TaskConfig` for inheritance structure
- [config.py](../src/pt/config.py#L180-L260) - Task inheritance logic in `resolve_task()`
- [runner.py](../src/pt/runner.py#L140-L200) - Condition evaluation and command building
- [parallel.py](../src/pt/parallel.py#L50-L120) - Failure modes and output handling
- [tests/test_conditions.py](../tests/test_conditions.py) - Condition evaluation examples

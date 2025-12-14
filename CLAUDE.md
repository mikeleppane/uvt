# pt - Python Task Runner

**pt** is a Python task runner built on `uv` for dependency isolation and environment management. It provides task orchestration, profiles, task inheritance, and PEP 723 support.

## Tech Stack

- **Python 3.10+** with strict type checking (mypy)
- **Pydantic v2** for configuration validation
- **Click** for CLI interface
- **Rich** for terminal output
- **asyncio** for parallel execution
- **uv** for dependency management and script execution

## Codebase Structure

- `models.py` - Pydantic schemas: PtConfig, TaskConfig, ProfileConfig, PipelineConfig, ConditionConfig
- `config.py` - Config loading, task inheritance resolution, profile/env merging, .env file loading
- `runner.py` - Task execution orchestration, hooks execution, condition checking, PEP 723 integration
- `executor.py` - UV command building, subprocess execution with timeout support
- `parallel.py` - Async parallel/sequential task execution with buffered/interleaved output
- `graph.py` - Dependency graph (DAG), topological sorting, cycle detection
- `script_meta.py` - PEP 723 inline metadata parser
- `dotenv.py` - .env file parsing with variable expansion (${VAR}, $VAR)
- `watch.py` - File watching with debounce for auto-rerun
- `cli.py` - Click commands: run, exec, multi, pipeline, list, tags, watch, check, init
- `completion.py` - Shell completion for bash/zsh/fish

### Test Files

- `tests/test_models.py` - Pydantic model validation tests
- `tests/test_config.py` - Config loading and inheritance tests
- `tests/test_executor.py` - UV command execution tests
- `tests/test_graph.py` - Dependency graph and cycle detection tests
- `tests/test_conditions.py` - Conditional execution tests
- `tests/test_script_meta.py` - PEP 723 metadata parsing tests
- `tests/test_hooks.py` - Task hooks execution tests
- `tests/test_tags.py` - Task tags filtering and validation tests
- `tests/test_completion.py` - Shell completion tests

## Key Concepts

**Task Inheritance**: Tasks extend parents via `extend` field. Merge rules:
- Override: script, cmd, cwd, timeout, python, description, hooks
- Merge (dedupe): dependencies, pythonpath, depends_on, tags
- Concatenate: args (parent args + child args)
- Merge dict: env (child overrides parent keys)

**Profiles**: Environment-specific configs (dev/ci/prod) with .env file support.
Merging order: global .env → global env → profile .env → profile env → task env

**PYTHONPATH**: Lists are merged and deduplicated across global/profile/task, not replaced.

**Conditional Execution**: Declarative (platform, env vars, files) + script-based conditions.

**PEP 723 Support**: Scripts declare inline dependencies in `# /// script` blocks.

**Task Hooks**: Execute scripts before/after tasks for setup, teardown, notifications, or cleanup.
- `before_task`: Runs before task. If fails, task is skipped.
- `after_success`: Runs only if task succeeds (exit code 0)
- `after_failure`: Runs only if task fails (exit code != 0)
- `after_task`: Always runs after task regardless of success/failure

Hook Environment:
- Inherit task's env, pythonpath, cwd, python version
- Receive special env vars: `PT_TASK_NAME`, `PT_HOOK_TYPE`, `PT_TASK_EXIT_CODE`
- Execute with same UvCommand pattern as condition scripts

Implementation: `runner.py:166-222` (`_execute_hook`, `_execute_hook_async`)

**Task Tags**: Organize and filter tasks by category (e.g., ci, testing, production).
- Alphanumeric characters with hyphens and underscores allowed
- Cannot be empty; validated via `@field_validator` in TaskConfig
- Merged from parent to child tasks, deduplicated and sorted alphabetically
- Merge rule: `parent.tags + child.tags → unique, sorted`

CLI Filtering:
- `pt list --tag <tag>`: Filter tasks by tag(s)
- `pt multi --tag <tag>`: Run tasks with tag(s)
- `pt tags`: List all tags with task counts
- `--match-any`: Use OR logic instead of AND

Implementation: `models.py:186,290-307`, `cli.py` (list, multi, tags commands)

## Development

```bash
pytest tests/              # Run tests
ruff format src/ tests/    # Format code
ruff check src/ tests/     # Lint
mypy src/                  # Type check
uv pip install -e .        # Install locally
python -m pt <command>     # Run CLI
```

## Patterns

- **Pydantic**: Strict validation with `ConfigDict(extra="forbid")`
- **Async/Sync Bridge**: Sync APIs wrap async via `asyncio.run()`
- **Error Handling**: Custom exceptions (ConfigError, CycleError) with user-friendly messages
- **Rich Output**: Console, Table, Progress for formatted display
- **Testing**: pytest with pytest-asyncio, use `tmp_path` fixture, `textwrap.dedent()` for TOML

## Documentation

- `README.md` - Full user documentation with examples and comparisons
- `PROJECT_ANALYSIS.md` - Strategic roadmap and competitive analysis
- Module docstrings - Detailed purpose and API documentation

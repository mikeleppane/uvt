# uvtx - Python Task Runner

**uvtx** is a modern Python task runner built on `uv` for dependency isolation and environment management. It provides task orchestration, profiles, task inheritance, PEP 723 support, variable templating, and flexible command execution.

## Tech Stack

- **Python 3.10+** with strict type checking (mypy)
- **Pydantic v2** for configuration validation
- **Click** for CLI interface
- **Rich** for terminal output
- **asyncio** for parallel execution
- **uv** for dependency management and script execution

## Codebase Structure

### Core Modules

- `models.py` - Pydantic schemas: PtConfig, TaskConfig, ProfileConfig, PipelineConfig, ConditionConfig
- `config.py` - Config loading, task inheritance resolution, profile/env merging, .env file loading, variable interpolation
- `runner.py` - Task execution orchestration, hooks execution, condition checking, PEP 723 integration
- `executor.py` - UV command building, subprocess execution with timeout support, output redirection
- `variables.py` - Variable interpolation engine with recursive expansion and circular reference detection
- `parallel.py` - Async parallel/sequential task execution with buffered/interleaved output
- `graph.py` - Dependency graph (DAG), topological sorting, cycle detection
- `script_meta.py` - PEP 723 inline metadata parser
- `dotenv.py` - .env file parsing with variable expansion (${VAR}, $VAR)
- `watch.py` - File watching with debounce for auto-rerun
- `cli.py` - Click commands: run (with inline support), exec, multi, pipeline, list, tags, watch, check, init
- `completion.py` - Shell completion for bash/zsh/fish

### Test Files

- `tests/test_models.py` - Pydantic model validation tests
- `tests/test_config.py` - Config loading and inheritance tests
- `tests/test_executor.py` - UV command execution tests
- `tests/test_variables.py` - Variable interpolation and templating tests
- `tests/test_graph.py` - Dependency graph and cycle detection tests
- `tests/test_conditions.py` - Conditional execution tests
- `tests/test_script_meta.py` - PEP 723 metadata parsing tests
- `tests/test_hooks.py` - Task hooks execution tests
- `tests/test_tags.py` - Task tags filtering and validation tests
- `tests/test_completion.py` - Shell completion tests
- `tests/test_parallel.py` - Parallel/sequential execution tests
- `tests/test_runner.py` - Task runner integration tests
- `tests/test_dotenv.py` - .env file parsing tests
- `tests/test_performance.py` - Performance benchmarks and regression tests

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
- Receive special env vars: `UVR_TASK_NAME`, `UVR_HOOK_TYPE`, `UVR_TASK_EXIT_CODE`
- Execute with same UvCommand pattern as condition scripts

Implementation: `runner.py:166-222` (`_execute_hook`, `_execute_hook_async`)

**Task Tags**: Organize and filter tasks by category (e.g., ci, testing, production).
- Alphanumeric characters with hyphens and underscores allowed
- Cannot be empty; validated via `@field_validator` in TaskConfig
- Merged from parent to child tasks, deduplicated and sorted alphabetically
- Merge rule: `parent.tags + child.tags → unique, sorted`

CLI Filtering:
- `uvtx list --tag <tag>`: Filter tasks by tag(s)
- `uvtx multi --tag <tag>`: Run tasks with tag(s)
- `uvtx tags`: List all tags with task counts
- `--match-any`: Use OR logic instead of AND

Implementation: `models.py:186,290-307`, `cli.py` (list, multi, tags commands)

**Variable Templating**: Reusable string interpolation across task configurations.

- Define variables in `[variables]` section (global) or per-profile
- Reference using `{variable}` syntax in task fields
- Opt-in via `use_vars = true` (global or per-task)
- Supports recursive variable expansion
- Circular reference detection with clear error messages
- Interpolates: cmd, script, args, env values, cwd, dependencies, hooks

Example:

```toml
[project]
use_vars = true

[variables]
src_dir = "src/myapp"
test_dir = "tests"

[tasks.lint]
cmd = "ruff check {src_dir}"

[profiles.ci]
variables = { src_dir = "build/src/myapp" }
```

Implementation: `variables.py` (interpolation engine), `config.py:apply_variable_interpolation()`, `models.py` (schema)

**Global Runner/Command Prefix**: Automatically prepend commands with a runner (e.g., "dotenv run").

- Define via `[project] runner = "..."`
- Profile-specific override via `[profiles.name] runner = "..."`
- Per-task opt-out via `disable_runner = true`
- Applies to both `cmd` and `script` tasks
- Hooks inherit runner from parent task

Example:

```toml
[project]
runner = "dotenv run"

[tasks.test]
cmd = "pytest tests/"  # Runs: uv run dotenv run pytest tests/

[tasks.raw]
cmd = "echo hello"
disable_runner = true  # Runs without runner
```

Implementation: `executor.py:UvCommand.build()`, `config.py:get_effective_runner()`, `models.py` (schema)

**Output Redirection**: Control where task output goes (files, null, inherit).

- Redirect stdout/stderr independently
- Special values: "null" (suppress), "inherit" (default)
- File paths (relative or absolute)
- Append mode for log files
- Auto-create parent directories

Example:

```toml
[tasks.build]
cmd = "python build.py"
stdout = "logs/build.log"
stderr = "logs/build.err"

[tasks.quiet]
cmd = "ruff check ."
stdout = "null"  # Suppress output
```

Implementation: `executor.py:_prepare_output_redirect()`, `executor.py:execute_sync()`, `models.py` (schema)

**Inline Task Definitions**: Run commands directly from CLI without config file.

- Use `--inline` flag to define command
- Supports `--env`, `--cwd`, `--timeout`, `--python` options
- Works with or without config file
- Respects global settings (runner, env, profile) if config present
- Inline env vars override config env

Example:

```bash
uvtx run --inline "pytest tests/" --env DEBUG=1
uvtx run --inline "python deploy.py" --env STAGE=prod --cwd workspace/
```

Implementation: `cli.py:_run_inline_task()`, `cli.py:run()` (command)

## Development

```bash
# Setup
uv sync --all-extras       # Install with dev dependencies

# Code Quality
uv run ruff format src/ tests/    # Format code
uv run ruff check src/ tests/     # Lint
uv run mypy src/                  # Type check
uv run pytest tests/              # Run tests
uv run pytest tests/ --cov=src/uvtx --cov-report=term-missing  # With coverage

# Running uvtx
uv run uvtx <command>        # Run CLI via uv
python -m uvtx <command>     # Run CLI directly
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
- `IMPLEMENTATION_COMPLETE.md` - Summary of newly implemented features
- Module docstrings - Detailed purpose and API documentation

## Recent Features (v0.1.0+)

Four major features were added to enhance uvtx's capabilities:

1. **Variable Templating** - Reusable `{variable}` syntax for DRY configurations
2. **Global Runner** - Automatic command prefixing (e.g., "dotenv run") for all tasks
3. **Output Redirection** - Control stdout/stderr destination (files, null, inherit)
4. **Inline Tasks** - Run commands from CLI without config file

All features are backward-compatible and opt-in. See individual sections above for detailed documentation.

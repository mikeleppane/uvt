# pt

[![CI](https://github.com/mikeleppane/pt/workflows/CI/badge.svg)](https://github.com/mikeleppane/pt/actions)
[![PyPI](https://img.shields.io/pypi/v/pt.svg)](https://pypi.org/project/pt/)
[![Python](https://img.shields.io/pypi/pyversions/pt.svg)](https://pypi.org/project/pt/)
[![License](https://img.shields.io/pypi/l/pt.svg)](https://github.com/mikeleppane/pt/blob/main/LICENSE)
[![codecov](https://codecov.io/gh/mikeleppane/pt/branch/main/graph/badge.svg)](https://codecov.io/gh/mikeleppane/pt)
[![Code style: ruff](https://img.shields.io/badge/code%20style-ruff-000000.svg)](https://github.com/astral-sh/ruff)
[![Type checked: mypy](https://img.shields.io/badge/type%20checked-mypy-blue.svg)](https://mypy-lang.org/)
[![uv](https://img.shields.io/endpoint?url=https://raw.githubusercontent.com/astral-sh/uv/main/assets/badge/v0.json)](https://github.com/astral-sh/uv)

**A modern Python task runner built for the [uv](https://docs.astral.sh/uv/) era.**

pt solves the common pain points of running Python scripts:

- ✅ **No virtual environment activation** - `uv` handles it automatically
- ✅ **No PYTHONPATH headaches** - configure once, use everywhere
- ✅ **No dependency conflicts** - isolated per-task environments
- ✅ **No configuration duplication** - task inheritance and profiles

## Features

### Core Features

- 🚀 **Zero setup**: Leverages `uv` for automatic dependency management
- 📦 **PYTHONPATH management**: Configure paths once, use everywhere
- 🎯 **Task definitions**: Reusable tasks with dependencies, env vars, and arguments
- 📜 **PEP 723 support**: Scripts can declare inline dependencies
- ⚡ **Parallel execution**: Run multiple tasks concurrently with smart failure handling
- 🔄 **Pipelines**: Multi-stage workflows perfect for CI/CD
- 🎭 **Conditional execution**: Run tasks based on platform, environment, or files
- 👀 **Watch mode**: Auto-rerun tasks when files change

### Advanced Features

- 🎨 **Profiles**: Environment-specific configurations (dev/staging/prod)
- 🔗 **Task inheritance**: Extend tasks to eliminate duplication
- 🏷️ **Aliases**: Multiple names for the same task
- 🪝 **Task hooks**: Run scripts before/after tasks for setup/teardown
- 🔖 **Task tags**: Organize and filter tasks by categories
- 📂 **Task categories**: Logical grouping for tasks (testing, build, deploy)
- 🚨 **Global error handler**: Centralized error recovery across all tasks
- 💾 **Built-in env vars**: Automatic context variables (project root, git info, CI detection)
- 🔒 **Private tasks**: Hide implementation details (tasks starting with `_`)
- 🌍 **.env file support**: Load environment variables from files
- 🔍 **Config discovery**: Automatically finds `pt.toml` in parent directories

## Installation

### Prerequisites

**pt requires [uv](https://docs.astral.sh/uv/) to be installed.** Install it first:

```bash
# Linux/macOS
curl -LsSf https://astral.sh/uv/install.sh | sh

# Windows
powershell -c "irm https://astral.sh/uv/install.ps1 | iex"

# Or via pip
pip install uv
```

### Install pt

```bash
# Using uv (recommended)
uv tool install pt

# Using pip
pip install pt

# From source
git clone https://github.com/mikeleppane/pt
cd pt
uv pip install -e .
```

## Quick Start

1. Create a `pt.toml` in your project root:

```toml
[project]
name = "my-project"

[env]
PYTHONPATH = ["src"]

[tasks.hello]
description = "Print hello world"
cmd = "python -c 'print(\"Hello from pt!\")'"

[tasks.test]
description = "Run tests"
cmd = "pytest"
dependencies = ["pytest", "pytest-cov"]
pythonpath = ["src", "tests"]
```

2. Run a task:

```bash
pt run hello
pt run test
```

## Core Concepts

### Config File Location

pt looks for configuration in:

1. `pt.toml` (preferred)
2. `pyproject.toml` under `[tool.pt]`

It searches from the current directory upward.

### Profiles

Profiles let you define environment-specific configurations without duplicating tasks. Perfect for dev/staging/prod environments.

```toml
[project]
name = "my-api"
default_profile = "dev"  # Used when no --profile specified

# Global .env files (loaded first)
env_files = [".env"]

[env]
API_URL = "http://localhost:8000"  # Default/fallback

# Development profile
[profiles.dev]
env = { DEBUG = "1", LOG_LEVEL = "debug" }
env_files = [".env.dev"]  # Profile-specific .env
python = "3.12"

# CI profile
[profiles.ci]
env = { CI = "1", LOG_LEVEL = "info" }
dependencies = { testing = ["pytest>=8.0", "coverage"] }

# Production profile
[profiles.prod]
env = { LOG_LEVEL = "error", WORKERS = "4" }
env_files = [".env.prod"]
python = "3.11"

[tasks.serve]
script = "src/server.py"
dependencies = ["fastapi", "uvicorn"]
```

**Usage:**

```bash
# Use default profile (dev)
pt run serve

# Explicit profile
pt run serve --profile prod

# Override via environment
PT_PROFILE=ci pt run test
```

**Priority order** (later overrides earlier):

1. Global .env files
2. Global env vars
3. Profile .env files
4. Profile env vars

### Task Inheritance

Reduce duplication by extending tasks. Child tasks inherit and override parent configuration.

```toml
# Base task
[tasks.test]
description = "Run tests"
cmd = "pytest"
dependencies = ["pytest"]
pythonpath = ["src", "tests"]

# Inherit and override
[tasks.test-verbose]
extend = "test"
description = "Run tests with verbose output"
args = ["-v", "-s"]  # Adds to parent args

[tasks.test-coverage]
extend = "test"
description = "Run tests with coverage"
dependencies = ["pytest-cov"]  # Merged with parent
args = ["--cov=src", "--cov-report=html"]

[tasks.test-watch]
extend = "test-verbose"
description = "Watch and run tests"
cmd = "pytest-watch"  # Overrides parent cmd
```

**Inheritance rules:**

- **Override**: `script`, `cmd`, `cwd`, `timeout`, `python`, `description`
- **Merge (no duplicates)**: `dependencies`, `pythonpath`, `depends_on`
- **Concatenate**: `args` (parent args + child args)
- **Merge dicts**: `env` (child overrides parent keys)

### Aliases and Private Tasks

**Aliases** provide shortcuts for frequently used tasks:

```toml
[tasks.format]
description = "Format all code"
cmd = "ruff format src/ tests/"
dependencies = ["ruff"]
aliases = ["f", "fmt"]  # Run with: pt run f

[tasks.lint]
description = "Lint code"
cmd = "ruff check src/"
dependencies = ["ruff"]
aliases = ["l"]

[tasks.typecheck]
description = "Type check code"
cmd = "mypy src/"
dependencies = ["mypy"]
aliases = ["t", "types"]
```

**Private tasks** (start with `_`) are hidden from `pt list`:

```toml
[tasks._setup-db]
description = "Internal: Initialize database"
script = "scripts/setup_db.py"

[tasks._cleanup]
description = "Internal: Clean temp files"
cmd = "rm -rf .cache __pycache__"

[tasks.ci]
description = "Run CI checks"
depends_on = ["_setup-db", "test", "_cleanup"]
# _setup-db and _cleanup won't show in `pt list`
# but are still runnable: pt run _setup-db
```

**List tasks:**

```bash
pt list              # Shows public tasks with aliases
pt list --all        # Shows private tasks too
pt list --verbose    # Shows full details
```

## Configuration Reference

### Full Example

```toml
[project]
name = "my-project"
python = "3.12"  # Default Python version

[env]
# Global environment variables
PYTHONPATH = ["src", "lib"]
DATABASE_URL = "postgres://localhost/dev"

[dependencies]
# Named dependency groups
common = ["requests", "pydantic>=2.0"]
testing = ["pytest", "pytest-cov"]
linting = ["ruff", "mypy"]

[tasks.format]
description = "Format code"
cmd = "ruff format src/"
dependencies = ["ruff"]

[tasks.lint]
description = "Run linting"
cmd = "ruff check src/"
dependencies = ["linting"]

[tasks.typecheck]
description = "Run type checking"
cmd = "mypy src/"
dependencies = ["mypy"]
env = { MYPYPATH = "src" }

[tasks.test]
description = "Run tests"
script = "scripts/run_tests.py"
dependencies = ["testing"]
pythonpath = ["src", "tests"]
args = ["--verbose"]

[tasks.check]
description = "Run all checks"
depends_on = ["lint", "typecheck", "test"]
parallel = true  # Run dependencies in parallel

[pipelines.ci]
description = "CI pipeline"
on_failure = "fail-fast"  # or "wait", "continue"
output = "buffered"  # or "interleaved"
stages = [
    { tasks = ["lint", "typecheck"], parallel = true },
    { tasks = ["test"] },
]
```

### Task Options

| Option | Type | Description |
|--------|------|-------------|
| `description` | string | Task description shown in `pt list` |
| `script` | string | Path to Python script to run |
| `cmd` | string | Shell command to run |
| `args` | list | Default arguments passed to script/cmd |
| `dependencies` | list | Package dependencies or group names (e.g., `["pytest"]`, `["testing"]`) |
| `env` | table | Task-specific environment variables |
| `pythonpath` | list | Additional paths to add to PYTHONPATH |
| `depends_on` | list | Other tasks that must run first |
| `parallel` | bool | Run `depends_on` tasks in parallel (default: false) |
| `python` | string | Python version for this task (e.g., `"3.12"`) |
| `cwd` | string | Working directory for task execution |
| `timeout` | int | Timeout in seconds (task killed if exceeded) |
| `ignore_errors` | bool | Continue even if task fails (exit code 0) |
| `condition` | table | Declarative conditions for task execution |
| `condition_script` | string | Script that must exit 0 for task to run |
| `extend` | string | Parent task to inherit from |
| `aliases` | list | Alternative names for this task |
| `tags` | list | Tags for organizing and filtering tasks |
| `before_task` | string | Hook script to run before task execution |
| `after_task` | string | Hook script to run after task (always runs) |
| `after_success` | string | Hook script to run only if task succeeds |
| `after_failure` | string | Hook script to run only if task fails |

### Task Hooks

Hooks allow you to run scripts before or after task execution, perfect for setup/teardown, notifications, or cleanup:

```toml
[tasks.deploy]
description = "Deploy application"
script = "scripts/deploy.py"
before_task = "scripts/pre_deploy_check.py"   # Pre-flight checks
after_success = "scripts/notify_success.sh"    # Send success notification
after_failure = "scripts/rollback.sh"          # Rollback on failure
after_task = "scripts/cleanup.py"              # Always cleanup temp files
```

**Hook Types:**
- `before_task`: Runs before the task. If it fails, the task is skipped.
- `after_success`: Runs only if the task succeeds (exit code 0).
- `after_failure`: Runs only if the task fails (exit code != 0).
- `after_task`: Always runs after the task, regardless of success or failure.

**Hook Environment Variables:**

Hooks receive these special environment variables:
- `PT_TASK_NAME`: Name of the task being run
- `PT_HOOK_TYPE`: Type of hook (`before_task`, `after_success`, etc.)
- `PT_TASK_EXIT_CODE`: Exit code of the task (for after hooks)

Hooks also inherit the task's environment variables and PYTHONPATH.

**Example: Database Migration with Backup**

```toml
[tasks.migrate]
description = "Run database migrations"
script = "scripts/migrate.py"
before_task = "scripts/backup_db.sh"      # Backup before migration
after_failure = "scripts/restore_db.sh"   # Restore if migration fails
after_task = "scripts/cleanup_backup.sh"  # Cleanup old backups
env = { DATABASE_URL = "postgresql://localhost/mydb" }
```

### Global Error Handler

The global error handler provides centralized error recovery across all tasks. Configure a task to run whenever any task fails:

```toml
[project]
name = "my-project"
on_error_task = "cleanup"  # Run this task when any task fails

[tasks.cleanup]
description = "Clean up after failures"
script = "scripts/cleanup_on_error.py"

[tasks.risky-task]
description = "Task that might fail"
script = "scripts/risky.py"
# If this fails, 'cleanup' will run automatically
```

**Error Handler Context:**

The error handler receives special environment variables about the failure:

```toml
[tasks.notify-failure]
description = "Send failure notification"
cmd = "bash"
args = ["-c", "echo Failed task: $PT_FAILED_TASK with code $PT_ERROR_CODE"]
```

| Variable | Description | Example |
|----------|-------------|---------|
| `PT_FAILED_TASK` | Name of the task that failed | `deploy` |
| `PT_ERROR_CODE` | Exit code of the failed task | `1` |
| `PT_ERROR_STDERR` | Error output from the failed task | `Connection refused` |

**Important Notes:**

- Error handler doesn't run for tasks with `ignore_errors = true`
- If the error handler itself fails, it won't trigger recursively
- Error handler runs after all task hooks complete
- In parallel execution, each failed task triggers the error handler

**Example: CI Cleanup**

```toml
[project]
on_error_task = "ci-cleanup"

[tasks.ci-cleanup]
description = "Clean up CI resources on failure"
script = "scripts/ci_cleanup.py"

[tasks.deploy]
description = "Deploy to production"
script = "scripts/deploy.py"

[tasks.test]
description = "Run tests"
cmd = "pytest tests/"
ignore_errors = false  # Failures will trigger ci-cleanup

[tasks.optional-check]
description = "Optional validation"
cmd = "scripts/validate.sh"
ignore_errors = true  # Failures won't trigger ci-cleanup
```

### Task Tags

Tags help organize and filter tasks, making it easy to run related tasks together:

```toml
[tasks.lint]
cmd = "ruff check src/"
tags = ["ci", "quality", "pre-commit"]

[tasks.test-unit]
cmd = "pytest tests/unit"
tags = ["ci", "testing", "fast"]

[tasks.test-integration]
cmd = "pytest tests/integration"
tags = ["ci", "testing", "slow"]

[tasks.deploy]
script = "deploy.py"
tags = ["production", "dangerous"]
```

**Using Tags:**

```bash
# List tasks with specific tag
pt list --tag ci

# List tasks with multiple tags (AND logic)
pt list --tag ci --tag fast

# List tasks with any of the tags (OR logic)
pt list --tag fast --tag slow --match-any

# Run all tasks with a tag
pt multi --tag ci --parallel

# List all available tags
pt tags
```

**Tag Inheritance:**

Tags are merged when using task inheritance:

```toml
[tasks.base-test]
cmd = "pytest"
tags = ["testing"]

[tasks.unit]
extend = "base-test"
args = ["tests/unit"]
tags = ["fast", "ci"]  # Will have: ["testing", "fast", "ci"]
```

### Task Categories

Categories provide a single, logical grouping for tasks (unlike tags which allow multiple attributes). They're perfect for organizing tasks by purpose:

```toml
[tasks.test-unit]
cmd = "pytest tests/unit"
category = "testing"

[tasks.test-integration]
cmd = "pytest tests/integration"
category = "testing"

[tasks.lint]
cmd = "ruff check src/"
category = "quality"

[tasks.format]
cmd = "ruff format src/"
category = "quality"

[tasks.build]
cmd = "python -m build"
category = "build"

[tasks.deploy]
script = "deploy.py"
category = "deployment"
```

**Using Categories:**

```bash
# List tasks in a category
pt list --category testing

# Run all tasks in a category
pt multi --category quality

# Run all quality checks in parallel
pt multi --category quality --parallel
```

**Category Inheritance:**

Categories inherit from parent tasks (can be overridden):

```toml
[tasks.base-test]
cmd = "pytest"
category = "testing"

[tasks.unit]
extend = "base-test"
args = ["tests/unit"]
# Inherits category "testing"

[tasks.deploy]
extend = "base-test"
script = "deploy.py"
category = "deployment"  # Overrides parent's category
```

**When to Use Categories vs Tags:**

- **Category:** Single logical group (testing, build, deployment, quality)
- **Tags:** Multiple attributes (ci, unit, integration, slow, fast)

```toml
[tasks.test-integration]
category = "testing"           # What type of task is it?
tags = ["ci", "slow", "e2e"]  # How should it be run/filtered?
```

### Conditional Execution

Tasks can be conditionally executed based on various criteria:

```toml
[tasks.deploy]
description = "Deploy to production"
script = "scripts/deploy.py"
condition = {
    platforms = ["linux"],      # Only on Linux
    env_set = ["CI", "DEPLOY_KEY"],  # These env vars must be set
    env_not_set = ["SKIP_DEPLOY"],   # This must NOT be set
    env_true = ["ENABLE_DEPLOY"],    # Must be "1", "true", "yes", "on"
    env_equals = { ENVIRONMENT = "production" },
    files_exist = ["dist/app.tar.gz"],
}

[tasks.setup-db]
description = "Initialize database"
cmd = "python scripts/init_db.py"
condition = { files_not_exist = [".db_initialized"] }
```

You can also use a condition script:

```toml
[tasks.conditional]
script = "main.py"
condition_script = "scripts/check_conditions.py"  # Must exit 0 to run
```

### PEP 723 Inline Dependencies

Scripts can declare their own dependencies:

```python
#!/usr/bin/env python3
# /// script
# dependencies = ["requests", "rich"]
# requires-python = ">=3.10"
# ///

import requests
from rich import print

# Your code here
```

pt merges inline dependencies with task config (task config takes precedence).

## CLI Reference

### Commands

```bash
# Run a task
pt run <task> [args...]
pt run test
pt run test --verbose
pt run t                    # Using alias

# Run with specific profile
pt run serve --profile prod
pt run test -p ci

# Run a script with pt context
pt exec script.py [args...]
pt exec script.py --profile dev

# Run multiple tasks
pt multi task1 task2 task3 --parallel
pt multi task1 task2 --sequential --on-failure=continue
pt multi --tag ci --parallel          # Run all tasks with 'ci' tag
pt multi --tag ci --tag fast          # Run tasks with both tags (AND)
pt multi --tag fast --tag slow --match-any  # Run tasks with either tag (OR)

# Run a pipeline
pt pipeline ci
pt pipeline deploy --profile prod

# Watch for changes and re-run
pt watch test                        # Watch *.py files
pt watch test -p "src/**/*.py"       # Custom pattern
pt watch test -p "**/*.py" -p "**/*.toml"  # Multiple patterns
pt watch lint --no-clear             # Don't clear screen
pt watch test --profile dev          # With profile

# List tasks and pipelines
pt list                    # Public tasks only
pt list --all              # Include private tasks (_prefix)
pt list --verbose          # Show full details
pt list -v -a              # Verbose + all tasks
pt list --tag ci           # Filter by tag
pt list --tag ci --tag fast  # Filter by multiple tags (AND)
pt list --tag fast --tag slow --match-any  # Filter by tags (OR)

# List all tags
pt tags                    # Show all tags with task counts

# Validate configuration
pt check

# Initialize new config
pt init
pt init --force            # Overwrite existing
```

### Global Options

Available on most commands:

| Option | Short | Description |
|--------|-------|-------------|
| `--profile PROFILE` | `-p` | **NEW:** Use specific profile (dev/ci/prod) |
| `--verbose` | `-v` | Show detailed output including commands |
| `--config PATH` | `-c` | Specify config file path |

### Command-Specific Options

**`pt run` / `pt exec` / `pt watch`:**

- `-p, --profile PROFILE` - Profile to use
- `-v, --verbose` - Show verbose output
- `-c, --config PATH` - Config file path

**`pt multi`:**

- `--parallel` - Run tasks in parallel
- `--sequential` - Run tasks sequentially (default)
- `--on-failure MODE` - `fail-fast` (default), `wait`, or `continue`
- `--output MODE` - `buffered` (default) or `interleaved`

**`pt list`:**

- `-a, --all` - **NEW:** Show private tasks (starting with `_`)
- `-v, --verbose` - Show aliases, dependencies, and descriptions

**`pt watch`:**

- `--pattern PATTERN` - File pattern to watch (can specify multiple)
- `-i, --ignore PATTERN` - Patterns to ignore
- `--debounce SECONDS` - Debounce time (default: 0.5)
- `--no-clear` - Don't clear screen on changes

### Environment Variables

**User-Set Variables:**

- `PT_PROFILE` - Default profile to use (overridden by `--profile`)
- `PYTHONPATH` - Merged with pt's PYTHONPATH configuration

**Built-in Variables (Automatically Set):**

pt automatically sets these environment variables for all tasks:

| Variable | Description | Example |
|----------|-------------|---------|
| `PT_TASK_NAME` | Canonical task name (even if called via alias) | `test` |
| `PT_PROJECT_ROOT` | Absolute path to project root | `/home/user/project` |
| `PT_CONFIG_FILE` | Path to config file | `/home/user/project/pt.toml` |
| `PT_PROFILE` | Active profile name (if using --profile) | `dev` |
| `PT_PYTHON_VERSION` | Python version from config | `3.11` |
| `PT_CATEGORY` | Task category (if set) | `testing` |
| `PT_TAGS` | Comma-separated task tags (sorted) | `ci,fast,unit` |
| `PT_CI` | `"true"` if running in CI environment | `true` |
| `PT_GIT_BRANCH` | Current git branch (best effort) | `main` |
| `PT_GIT_COMMIT` | Current git commit SHA (best effort) | `abc123...` |

Use these variables in your tasks:

```toml
[tasks.deploy]
description = "Deploy from current branch"
cmd = "echo Deploying from $PT_GIT_BRANCH"

[tasks.show-context]
description = "Show task context"
script = "scripts/show_context.py"
# Script will have access to all PT_* variables
```

**Note:** Built-in variables have the lowest priority. User-defined variables (in `env` sections) can override them if needed.

## Use Cases

### CI/CD with Profiles

Use profiles to run the same tasks in different environments:

```toml
[project]
name = "my-app"
default_profile = "dev"

# CI profile with strict settings
[profiles.ci]
env = { CI = "1", STRICT_MODE = "1" }
dependencies = { testing = ["pytest>=8.0", "coverage>=7.0"] }

# Base test task
[tasks.test]
cmd = "pytest tests/"
dependencies = ["testing"]
aliases = ["t"]

# Coverage variant (extends base)
[tasks.test-cov]
extend = "test"
description = "Run tests with coverage"
args = ["--cov=src", "--cov-report=xml"]

[tasks._install-deps]
description = "Internal: Install dependencies"
cmd = "echo 'Dependencies handled by uv'"

[pipelines.ci]
description = "Full CI pipeline"
stages = [
    { tasks = ["lint", "typecheck"], parallel = true },
    { tasks = ["test-cov"] },
    { tasks = ["build"] },
]
```

**GitHub Actions:**

```yaml
# .github/workflows/ci.yml
name: CI
on: [push, pull_request]

jobs:
  test:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: astral-sh/setup-uv@v3
      - run: uvx pt pipeline ci --profile ci
```

### Multi-Environment Development

Manage dev, staging, and production with profiles:

```toml
[project]
name = "api-service"

# .env files
env_files = [".env"]

# Development
[profiles.dev]
env = { DEBUG = "1", LOG_LEVEL = "debug", API_URL = "http://localhost:8000" }
env_files = [".env.dev"]
python = "3.12"

# Staging
[profiles.staging]
env = { LOG_LEVEL = "info", API_URL = "https://staging.example.com" }
env_files = [".env.staging"]

# Production
[profiles.prod]
env = { LOG_LEVEL = "warning", API_URL = "https://api.example.com" }
env_files = [".env.prod"]
python = "3.11"

[tasks.serve]
description = "Start API server"
script = "src/main.py"
dependencies = ["fastapi", "uvicorn"]
aliases = ["s", "start"]

[tasks.deploy]
description = "Deploy to environment"
script = "scripts/deploy.py"
condition = { env_set = ["DEPLOY_KEY"] }
```

**Usage:**

```bash
# Development
pt run serve                    # Uses default dev profile
pt run s                        # Using alias

# Staging
pt run serve --profile staging

# Production
pt run deploy --profile prod
```

### DRY Task Definitions

Eliminate duplication with task inheritance:

```toml
# Base linting task
[tasks.lint]
description = "Lint code"
cmd = "ruff check"
dependencies = ["ruff"]
aliases = ["l"]

# Lint with auto-fix
[tasks.lint-fix]
extend = "lint"
description = "Lint and auto-fix issues"
args = ["--fix"]
aliases = ["lf"]

# Lint specific directory
[tasks.lint-tests]
extend = "lint"
description = "Lint test files only"
args = ["tests/"]

# Base test task
[tasks.test]
cmd = "pytest"
dependencies = ["pytest"]
pythonpath = ["src", "tests"]
aliases = ["t"]

# Test variants
[tasks.test-verbose]
extend = "test"
args = ["-v", "-s"]
aliases = ["tv"]

[tasks.test-watch]
extend = "test"
cmd = "pytest-watch"
dependencies = ["pytest-watch"]

[tasks.test-failed]
extend = "test"
description = "Re-run only failed tests"
args = ["--lf"]
aliases = ["tf"]
```

### Git Hooks with Private Tasks

Use private tasks for setup/cleanup:

```toml
[tasks._format-staged]
description = "Internal: Format staged files"
cmd = "git diff --cached --name-only --diff-filter=ACM '*.py' | xargs ruff format"

[tasks._check-types]
description = "Internal: Quick type check"
cmd = "mypy src/ --no-error-summary"
dependencies = ["mypy"]

[tasks.pre-commit]
description = "Run pre-commit checks"
depends_on = ["_format-staged", "_check-types"]
aliases = ["pc"]
```

**Git hook (`.git/hooks/pre-commit`):**

```bash
#!/bin/sh
pt run pre-commit || exit 1
```

### Complex Workflows

Combine all features for powerful workflows:

```toml
[project]
name = "data-pipeline"
default_profile = "dev"

[profiles.dev]
env = { ENV = "dev", WORKERS = "1" }

[profiles.prod]
env = { ENV = "prod", WORKERS = "4" }

# Private setup tasks
[tasks._check-data]
cmd = "test -f data/input.csv"
ignore_errors = false

[tasks._cleanup-temp]
cmd = "rm -rf /tmp/pipeline-*"
ignore_errors = true

# Main tasks
[tasks.process]
description = "Process data"
script = "scripts/process.py"
depends_on = ["_check-data"]
dependencies = ["pandas", "numpy"]
aliases = ["p"]

[tasks.process-parallel]
extend = "process"
description = "Process with multiple workers"
env = { PARALLEL = "1" }

# Workflow
[tasks.full-pipeline]
description = "Run complete pipeline"
depends_on = ["_check-data", "process", "_cleanup-temp"]

[pipelines.production]
description = "Production pipeline"
on_failure = "fail-fast"
stages = [
    { tasks = ["_check-data"] },
    { tasks = ["process-parallel"] },
    { tasks = ["_cleanup-temp"] },
]
```

**Usage:**

```bash
# Development
pt run process

# Production
pt pipeline production --profile prod
```

## Shell Completion

pt supports tab completion for Bash, Zsh, and Fish shells. Completions are context-aware and dynamically load task names, profile names, and pipeline names from your `pt.toml`.

### Bash

Add to `~/.bashrc`:

```bash
eval "$(_PT_COMPLETE=bash_source pt)"
```

Or install the completion file:

```bash
_PT_COMPLETE=bash_source pt > ~/.local/share/bash-completion/completions/pt
```

### Zsh

Add to `~/.zshrc`:

```zsh
eval "$(_PT_COMPLETE=zsh_source pt)"
```

Or install the completion file:

```zsh
_PT_COMPLETE=zsh_source pt > ~/.zsh/completions/_pt
# Ensure ~/.zsh/completions is in your $fpath
```

### Fish

```fish
_PT_COMPLETE=fish_source pt > ~/.config/fish/completions/pt.fish
```

### Completion Features

- **Task names** - Complete all public tasks and their aliases
- **Profile names** - Complete configured profiles (dev, ci, prod, etc.)
- **Pipeline names** - Complete defined pipelines
- **CLI options** - Complete all flags and options
- **Contextual** - Completions adapt to your `pt.toml` configuration

## Development

See [CONTRIBUTING.md](CONTRIBUTING.md) for development setup, testing, and contribution guidelines.

**Quick start**:

```bash
# Clone and setup
git clone https://github.com/your-username/pt.git
cd pt
uv sync --all-extras
uv run pre-commit install

# Run tests
uv run pytest tests/

# Run all checks (CI)
uv run ruff format src/ tests/
uv run ruff check src/ tests/
uv run mypy src/
uv run pytest tests/ --cov=src/pt
```

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

See [CONTRIBUTING.md](CONTRIBUTING.md) for detailed guidelines.

## License

MIT

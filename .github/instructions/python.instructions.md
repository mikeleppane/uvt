---
description: 'Python coding conventions and guidelines for pt'
applyTo: '**/*.py'
---

# Python Development Guidelines for `pt`

## Project Standards

### Code Style

- **Line length**: 100 characters (enforced by ruff, configured in pyproject.toml)
- **Indentation**: 4 spaces (no tabs)
- **Type hints**: Required for all function signatures and class attributes
- **Docstrings**: Required for all public functions, classes, and modules
- **Imports**: Absolute imports only (no relative imports except within package)

### Type Hinting (Python 3.10+ Syntax)

Use `from __future__ import annotations` at the top of files to enable forward references and cleaner type evaluation.

Use modern type hint syntax with `|` for unions and `list`/`dict` instead of `List`/`Dict`:

```python
# ✅ CORRECT - Modern Python 3.10+ syntax
def process_tasks(
    tasks: list[str],
    config: PtConfig,
    parallel: bool = False,
) -> dict[str, ExecutionResult]:
    """Process tasks and return execution results."""
    ...

def load_config(path: Path | None = None) -> tuple[PtConfig, Path]:
    """Load configuration from file or auto-discover."""
    ...

# ❌ WRONG - Old typing module syntax
from typing import List, Dict, Optional, Union
def process_tasks(
    tasks: List[str],
    config: PtConfig,
    parallel: Optional[bool] = False,
) -> Dict[str, ExecutionResult]:
    ...
```

### Pydantic v2 Patterns

**Model Definition with Strict Validation:**

```python
from pydantic import BaseModel, Field, ConfigDict

class TaskConfig(BaseModel):
    """Configuration for a single task."""

    model_config = ConfigDict(extra="forbid")  # Reject unknown fields

    script: str | None = None
    cmd: str | None = None
    args: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
```

**Field Validators:**

```python
from pydantic import field_validator

@field_validator("tags")
@classmethod
def validate_tags(cls, v: list[str]) -> list[str]:
    """Validate tag names are non-empty and alphanumeric."""
    for tag in v:
        if not tag:
            raise ValueError("Tag cannot be empty")
        if not tag.replace("-", "").replace("_", "").isalnum():
            msg = f"Tag '{tag}' must be alphanumeric (hyphens/underscores allowed)"
            raise ValueError(msg)
    return v
```

**Model Validators (Validate After All Fields Set):**

```python
from pydantic import model_validator
from typing_extensions import Self  # Requires typing-extensions (included with Pydantic)

@model_validator(mode="after")
def validate_script_or_cmd(self) -> Self:
    """Ensure task has either script, cmd, or depends_on."""
    has_execution = self.script is not None or self.cmd is not None
    has_depends_on = len(self.depends_on) > 0
    has_extend = self.extend is not None

    if not has_execution and not has_depends_on and not has_extend:
        raise ValueError("Task must have either 'script', 'cmd', or 'depends_on'")

    if self.script is not None and self.cmd is not None:
        raise ValueError("Task cannot have both 'script' and 'cmd'")

    return self
```

### Async/Await Patterns

**Async/Sync Bridge Pattern:**

Public APIs are synchronous (for CLI ease), internal execution is async:

```python
import asyncio

# Public sync API
def run_tasks(self, names: list[str]) -> dict[str, ExecutionResult]:
    """Run multiple tasks (sync wrapper)."""
    return asyncio.run(self.run_tasks_async(names))

# Internal async implementation
async def run_tasks_async(
    self,
    names: list[str],
) -> dict[str, ExecutionResult]:
    """Run multiple tasks asynchronously."""
    # Actual async implementation
    ...
```

**⚠️ Important:** Never nest `asyncio.run()` calls. Use it only at API boundaries.

**Async Executors (Protocol Pattern):**

Async executor functions must match the `TaskExecutor` protocol signature:

```python
import asyncio
from collections.abc import Coroutine
from typing import Any, Protocol

class TaskExecutor(Protocol):
    """Protocol for async task execution functions."""

    def __call__(
        self,
        task_name: str,  # Must be named task_name, not name
        output_queue: asyncio.Queue[tuple[str, str]] | None,
    ) -> Coroutine[Any, Any, ExecutionResult]: ...

# Implementation must match protocol
async def executor(
    task_name: str,  # ← Must match protocol name
    output_queue: asyncio.Queue[tuple[str, str]] | None,
) -> ExecutionResult:
    task = self.config.get_task(task_name)
    command = self.build_command(task)
    return await execute_async(command, task_name=task_name)
```

### Error Handling

**Custom Exceptions with Context:**

```python
# Exception Hierarchy
class PtError(Exception):
    """Base exception for all pt errors."""

class ConfigError(PtError):
    """Configuration is invalid or cannot be loaded."""

class ConfigNotFoundError(ConfigError):
    """No configuration file found."""

class TaskError(PtError):
    """Task execution or configuration error."""

class CycleError(TaskError):
    """Circular task dependency detected."""

class UnknownTaskError(TaskError):
    """Referenced task does not exist."""
```

**User-Friendly Error Messages:**

Always provide actionable context in error messages:

```python
# ✅ GOOD - Actionable message with context
if not config_path.exists():
    msg = (
        f"Config file not found: {config_path}\n"
        f"Run 'pt init' to create a configuration file."
    )
    raise ConfigNotFoundError(msg)

# ❌ BAD - Generic message
if not config_path.exists():
    raise FileNotFoundError("File not found")
```

**Validation Error Formatting:**

```python
from pydantic import ValidationError

def _format_validation_errors(error: ValidationError) -> str:
    """Format Pydantic errors for user-friendly display."""
    lines: list[str] = []
    for err in error.errors():
        loc = ".".join(str(part) for part in err["loc"])
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)
```

**Exception Chaining:**

Always preserve original exception context:

```python
import subprocess

# ✅ GOOD - Preserve original exception context
try:
    subprocess.run(command, check=True)
except subprocess.CalledProcessError as e:
    msg = f"Task '{task_name}' failed with exit code {e.returncode}"
    raise TaskError(msg) from e  # ← Preserve with 'from'

# ❌ BAD - Loses original stack trace
except subprocess.CalledProcessError as e:
    raise TaskError(f"Task failed: {e}")
```

### Logging

Use Python's `logging` module for debug/internal messages, Rich console for user-facing output:

```python
import logging
from rich.console import Console

console = Console()
logger = logging.getLogger(__name__)

# ✅ CORRECT - Internal debug info
logger.debug("Resolving task dependencies for: %s", task_name)
logger.info("Loading config from: %s", config_path)
logger.warning("Task '%s' has no dependencies", task_name)

# ✅ CORRECT - User-facing messages
console.print("[green]✓[/green] Task completed successfully")
console.print("[yellow]Warning:[/yellow] Config file not found")

# ❌ WRONG - Don't use print() for any output
print("Task completed")
print(f"Debug: {task_name}")  # Use logger.debug() instead
```

**Logging Configuration:**

```python
import logging

# In __main__.py or CLI entry point
def setup_logging(verbose: bool = False) -> None:
    """Configure logging based on verbosity level."""
    level = logging.DEBUG if verbose else logging.WARNING
    logging.basicConfig(
        level=level,
        format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    )
```

### Rich Console Output

**Color Conventions:**

- **Cyan**: Task names, command names, identifiers
- **Green**: Success states, tags, checkmarks
- **Yellow**: Warnings, skipped items, notices
- **Red**: Errors, failures, critical issues
- **Dim**: Secondary/meta information

**Console Usage:**

```python
from rich.console import Console
from rich.table import Table

console = Console()

# Status messages
console.print("[cyan]Running task:[/cyan] test")
console.print("[green]✓[/green] Task completed successfully")
console.print("[yellow]⚠[/yellow] Task skipped: condition not met")
console.print("[red]✗[/red] Task failed with exit code 1")

# Tables for structured data
table = Table(title="Tasks")
table.add_column("Name", style="cyan")
table.add_column("Tags", style="green")
table.add_row("test", "ci, fast")
console.print(table)
```

### Path Handling

**Always use `pathlib.Path`:**

```python
from pathlib import Path

# ✅ CORRECT
config_path = Path("uvt.toml")
script_path = Path(task.script)
resolved = (project_root / script_path).resolve()

# ❌ WRONG
import os.path
config_path = "uvt.toml"
script_path = os.path.join(project_root, task.script)
```

**Project-Relative Path Resolution:**

```python
def resolve_path(path: str, project_root: Path) -> Path:
    """Resolve a path relative to project root.

    Args:
        path: Path to resolve (relative or absolute).
        project_root: Project root directory.

    Returns:
        Resolved absolute path.
    """
    p = Path(path)
    if p.is_absolute():
        return p
    return (project_root / p).resolve()
```

### Testing Patterns

**Test Class Structure:**

```python
from pathlib import Path
from textwrap import dedent
import pytest

class TestTaskHooks:
    """Test suite for task hook execution."""

    def test_before_task_hook_success(self, tmp_path: Path) -> None:
        """Test that before_task hook runs before the task."""
        # Create hook script
        hook_script = tmp_path / "before_hook.py"
        hook_script.write_text('print("hook ran")')

        # Create config with dedent for TOML
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo test"
                before_task = "before_hook.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        assert result.success
```

**Async Test Pattern:**

```python
# pytest-asyncio handles async tests automatically (asyncio_mode = "auto")
async def test_parallel_execution(self, tmp_path: Path) -> None:
    """Test async parallel task execution."""
    config = setup_test_config(tmp_path)
    runner = Runner(config=config, project_root=tmp_path)

    results = await runner.run_tasks_async(
        ["task1", "task2"],
        parallel=True,
    )

    assert all(r.success for r in results.values())
```

**Use `tmp_path` for File Operations:**

```python
def test_config_loading(tmp_path: Path) -> None:
    """Test configuration file loading."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text('[project]\nname = "test"')

    config, path = load_config(config_file)
    assert config.project.name == "test"
    assert path == config_file
```

**Parameterized Tests:**

```python
import pytest

@pytest.mark.parametrize(
    "input_value,expected",
    [
        ("true", True),
        ("1", True),
        ("yes", True),
        ("on", True),
        ("false", False),
        ("0", False),
        ("no", False),
    ],
    ids=["true", "one", "yes", "on", "false", "zero", "no"],
)
def test_env_true_values(input_value: str, expected: bool) -> None:
    """Test various truthy/falsy environment variable values."""
    import os
    
    os.environ["TEST_VAR"] = input_value
    try:
        result = is_env_true("TEST_VAR")
        assert result == expected
    finally:
        del os.environ["TEST_VAR"]
```

**Test Fixtures:**

```python
import pytest
from pathlib import Path
from textwrap import dedent

@pytest.fixture
def sample_config(tmp_path: Path) -> Path:
    """Create a sample configuration file for testing."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        dedent("""\
            [project]
            name = "test-project"
            
            [tasks.test]
            cmd = "pytest"
            
            [tasks.lint]
            cmd = "ruff check"
        """)
    )
    return config_file

def test_task_loading(sample_config: Path) -> None:
    """Test loading tasks from config."""
    config = load_config(sample_config)
    assert "test" in config.tasks
    assert "lint" in config.tasks
```

**Cleanup with Fixtures:**

```python
import os
import pytest

@pytest.fixture
def clean_env():
    """Ensure clean environment for tests."""
    old_env = os.environ.copy()
    yield
    # Restore original environment
    os.environ.clear()
    os.environ.update(old_env)

def test_with_env(clean_env) -> None:
    """Test runs with clean environment."""
    os.environ["TEST_VAR"] = "value"
    # No cleanup needed - fixture handles it
```

### Documentation

**Module Docstrings:**

```python
"""Task runner orchestration - the main entry point for executing tasks."""
```

**Function Docstrings (Google Style):**

```python
def merge_env(
    *env_dicts: dict[str, str],
    pythonpath_lists: list[list[str]] | None = None,
    project_root: Path | None = None,
) -> dict[str, str]:
    """Merge multiple environment dictionaries.

    PYTHONPATH is handled specially by appending paths rather than replacing.
    Later dicts override earlier ones for all other keys.

    Args:
        *env_dicts: Environment dictionaries to merge (later wins).
        pythonpath_lists: Additional PYTHONPATH entries to append.
        project_root: Project root for resolving relative paths.

    Returns:
        Merged environment dictionary with PYTHONPATH properly combined.
    """
    ...
```

### Security Guidelines

**Command Injection Prevention:**

```python
import subprocess

# ✅ GOOD - Use list form, not shell=True
subprocess.run(["uv", "run", "pytest"], check=True)

# ✅ GOOD - If shell needed, validate input strictly
allowed_commands = {"test", "lint", "format"}
if task_name not in allowed_commands:
    raise ValueError(f"Invalid task: {task_name}")

# ❌ DANGEROUS - Shell injection risk
cmd = f"uv run {user_input}"  # user_input could be "; rm -rf /"
subprocess.run(cmd, shell=True)  # NEVER do this
```

**Path Traversal Prevention:**

```python
from pathlib import Path

def resolve_path(path: str, project_root: Path) -> Path:
    """Resolve and validate path is within project root.
    
    Args:
        path: Path to resolve (relative or absolute).
        project_root: Project root directory.
        
    Returns:
        Resolved absolute path.
        
    Raises:
        ValueError: If path is outside project root.
    """
    p = Path(path)
    if p.is_absolute():
        resolved = p.resolve()
    else:
        resolved = (project_root / p).resolve()
    
    # Ensure resolved path is within project root
    try:
        resolved.relative_to(project_root)
    except ValueError:
        msg = f"Path '{path}' is outside project root"
        raise ValueError(msg) from None
    
    return resolved
```

### CLI Patterns (Click)

**Command Structure:**

```python
import click
from rich.console import Console

console = Console()

@click.command()
@click.option("--quiet", "-q", is_flag=True, help="Suppress output")
@click.option("--verbose", "-v", is_flag=True, help="Show debug output")
@click.argument("task_names", nargs=-1, required=True)
def run(task_names: tuple[str, ...], quiet: bool, verbose: bool) -> None:
    """Run one or more tasks."""
    try:
        setup_logging(verbose)
        runner = Runner.from_config_file()
        results = runner.run_tasks(list(task_names))
        
        if not quiet:
            display_results(results)
            
        # Exit with non-zero if any task failed
        if any(not r.success for r in results.values()):
            raise SystemExit(1)
            
    except (ConfigError, TaskError) as e:
        console.print(f"[red]Error:[/red] {e}")
        raise SystemExit(1) from e
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        raise SystemExit(130)  # Standard interrupt exit code
```

**Exit Code Conventions:**

- `0`: Success - all tasks completed successfully
- `1`: Failure - task failed or configuration error
- `2`: Invalid arguments - wrong command-line usage
- `130`: Interrupted - user pressed Ctrl+C

### Context Managers

Use context managers for resource cleanup and temporary state:

```python
import os
from contextlib import contextmanager
from pathlib import Path

@contextmanager
def temp_env_vars(**env_vars: str):
    """Temporarily set environment variables.
    
    Args:
        **env_vars: Environment variables to set temporarily.
        
    Yields:
        None
        
    Example:
        >>> with temp_env_vars(DEBUG="1", LOG_LEVEL="info"):
        ...     run_task("test")
    """
    old_env: dict[str, str | None] = {}
    for key, value in env_vars.items():
        old_env[key] = os.environ.get(key)
        os.environ[key] = value
    
    try:
        yield
    finally:
        for key, old_value in old_env.items():
            if old_value is None:
                os.environ.pop(key, None)
            else:
                os.environ[key] = old_value

@contextmanager
def temp_cwd(path: Path):
    """Temporarily change working directory."""
    old_cwd = Path.cwd()
    os.chdir(path)
    try:
        yield
    finally:
        os.chdir(old_cwd)
```

### Performance Guidelines

**Avoid Repeated Expensive Operations:**

```python
from functools import cached_property

class TaskRunner:
    def __init__(self, config_path: Path):
        self.config_path = config_path
        
    # ❌ BAD - Recomputes on every access
    @property
    def all_deps(self) -> list[str]:
        return self._compute_dependencies()  # Expensive operation
    
    # ✅ GOOD - Cache the result (computed once)
    @cached_property
    def all_deps(self) -> list[str]:
        return self._compute_dependencies()
```

**Use Lazy Evaluation:**

```python
class TaskRunner:
    def __init__(self, config_path: Path | None = None):
        self._config_path = config_path
        self._config: PtConfig | None = None
        
    # ✅ GOOD - Only load config when first accessed
    @property
    def config(self) -> PtConfig:
        if self._config is None:
            self._config = load_config(self._config_path)
        return self._config
```

**Prefer Generator Expressions:**

```python
# ✅ GOOD - Memory efficient for large datasets
task_names = (task.name for task in tasks if task.enabled)
results = process_tasks(task_names)

# ❌ AVOID - Creates full list in memory
task_names = [task.name for task in tasks if task.enabled]
results = process_tasks(task_names)
```

## Common Patterns in `pt`

### Environment Variable Merging

```python
# PYTHONPATH is additive, not replacing
result_env = merge_env(
    global_env,
    profile_env,
    task_env,
    pythonpath_lists=[task.pythonpath] if task.pythonpath else None,
    project_root=self.project_root,
)
```

### Task Hook Execution Order

```python
# Hooks execute in this specific order:
# 1. before_task (if fails, task is skipped)
# 2. task execution
# 3. after_success OR after_failure (based on task result)
# 4. after_task (always runs, regardless of success/failure)
```

### Tag Validation and Filtering

```python
# Tags are case-sensitive and validated
# Valid: "ci", "pre-commit", "unit_test"
# Invalid: "ci test" (spaces), "" (empty), "ci!" (special chars)

# Filter tasks by tags
ci_tasks = config.get_tasks_by_tag("ci")
fast_ci_tasks = config.get_tasks_by_tags(["ci", "fast"], match_all=True)
```

### Dependency Resolution

```python
# Dependencies can be:
# 1. Direct package specs: "pytest>=8.0"
# 2. Group references: "testing" (resolved from config.dependencies)
# 3. PEP 723 inline deps (merged with task deps, deduplicated)

all_deps = merge_dependencies(script_deps, config_deps)
```

## Anti-Patterns to Avoid

### ❌ Don't Use Relative Imports in Tests

```python
# ❌ BAD
from ..pt.config import load_config

# ✅ GOOD
from pt.config import load_config
```

### ❌ Don't Mutate Pydantic Models

```python
# ❌ BAD
task.tags.append("new-tag")  # Mutates model

# ✅ GOOD
task = task.model_copy(update={"tags": task.tags + ["new-tag"]})
```

### ❌ Don't Catch Generic Exceptions

```python
# ❌ BAD
try:
    config = load_config(path)
except Exception as e:
    print(f"Error: {e}")

# ✅ GOOD
try:
    config = load_config(path)
except (ConfigError, ConfigNotFoundError) as e:
    console.print(f"[red]Config error:[/red] {e}")
except ValidationError as e:
    console.print(f"[red]Validation error:[/red]\n{_format_validation_errors(e)}")
```

### ❌ Don't Use os.path

```python
# ❌ BAD
import os.path
full_path = os.path.join(root, "tasks", "test.py")

# ✅ GOOD
from pathlib import Path
full_path = root / "tasks" / "test.py"
```

### ❌ Don't Hardcode Paths

```python
# ❌ BAD
def test_config():
    config = load_config("/tmp/test/uvt.toml")

# ✅ GOOD
def test_config(tmp_path: Path):
    config_file = tmp_path / "uvt.toml"
    config = load_config(config_file)
```

### ❌ Don't Use Old typing Module Syntax

```python
# ❌ BAD
from typing import List, Dict, Optional, Union

def func(items: Optional[List[str]]) -> Dict[str, int]:
    ...

# ✅ GOOD - Use Python 3.10+ syntax
def func(items: list[str] | None) -> dict[str, int]:
    ...
```

## Code Review Checklist

Before submitting code, verify:

**Type Safety & Documentation:**
- [ ] Type hints on all function signatures and class attributes
- [ ] Docstrings on public functions, classes, and modules
- [ ] No `typing.List`/`Dict`/`Optional` (use `list`/`dict`/`|None`)
- [ ] Complete imports in all code examples

**Code Quality:**
- [ ] Line length ≤ 100 characters
- [ ] Imports are absolute (not relative, except within package)
- [ ] Path operations use `pathlib.Path` (not `os.path`)
- [ ] No hardcoded file paths in tests

**Error Handling:**
- [ ] Error messages provide actionable context
- [ ] Exceptions preserve context with `raise ... from e`
- [ ] Don't catch generic `Exception` without good reason

**Security:**
- [ ] No `shell=True` in subprocess calls unless necessary and validated
- [ ] User input validated before use in commands or paths
- [ ] Paths validated to prevent directory traversal

**Pydantic Models:**
- [ ] Models use `ConfigDict(extra="forbid")`
- [ ] Field validators for custom validation
- [ ] Model validators use `mode="after"` when checking multiple fields

**Async/Await:**
- [ ] Async functions properly await (no blocking calls)
- [ ] `asyncio.run()` only used at API boundaries (not nested)

**Testing:**
- [ ] Tests use `tmp_path` fixture for file operations
- [ ] Parameterized tests for multiple input variations
- [ ] Fixtures for complex test setup
- [ ] Async tests properly awaited

**Output & Logging:**
- [ ] Console output uses Rich with proper colors
- [ ] Logging used for debug info, console for user messages
- [ ] No bare `print()` statements

**CLI (if applicable):**
- [ ] Exit codes follow conventions (0=success, 1=error, 2=invalid args, 130=interrupt)
- [ ] User-facing errors caught and formatted nicely
- [ ] `--verbose` flag enables debug logging

**Performance:**
- [ ] Expensive operations cached with `@cached_property` if needed
- [ ] Resources properly cleaned up (use context managers)

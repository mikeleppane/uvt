"""CLI commands for pt using click."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.table import Table

from pt import __version__
from pt.completion import complete_pipeline_name, complete_profile_name, complete_task_name
from pt.config import ConfigError, ConfigNotFoundError, load_config
from pt.executor import check_uv_installed
from pt.models import OnFailure, OutputMode
from pt.runner import Runner

# Heavy imports loaded lazily inside commands that use them:
# - pt.watch (only for watch command)
# - rich.panel (only for init command)

console = Console()


def print_uv_not_installed_error() -> None:
    """Print a helpful error message when uv is not installed."""
    console.print("[red]Error:[/red] uv is not installed.")
    console.print("\n[bold]Install uv:[/bold]")
    console.print("  • Linux/macOS: [cyan]curl -LsSf https://astral.sh/uv/install.sh | sh[/cyan]")
    console.print("  • Windows:     [cyan]powershell -c \"irm https://astral.sh/uv/install.ps1 | iex\"[/cyan]")
    console.print("  • pip:         [cyan]pip install uv[/cyan]")
    console.print("\n[dim]Or visit: https://docs.astral.sh/uv/getting-started/installation/[/dim]")


def handle_errors(func: Any) -> Any:
    """Decorator to handle common errors with nice output."""
    import functools

    @functools.wraps(func)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        try:
            return func(*args, **kwargs)
        except ConfigNotFoundError as e:
            console.print(f"[red]Error:[/red] {e}")
            console.print("\n[dim]Run 'pt init' to create a configuration file.[/dim]")
            sys.exit(1)
        except ConfigError as e:
            console.print(f"[red]Configuration error:[/red]\n{e}")
            sys.exit(1)
        except KeyError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
        except KeyboardInterrupt:
            console.print("\n[yellow]Interrupted[/yellow]")
            sys.exit(130)

    return wrapper


@click.group()
@click.version_option(version=__version__, prog_name="pt")
def main() -> None:
    """pt - A Python task runner for Python scripts using uv."""
    pass


@main.command()
@click.argument("task_name", shell_complete=complete_task_name)
@click.argument("args", nargs=-1)
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.option(
    "-p",
    "--profile",
    "profile",
    shell_complete=complete_profile_name,
    help="Profile to use (dev, ci, prod, etc.)",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def run(
    task_name: str,
    args: tuple[str, ...],
    verbose: bool,
    profile: str | None,
    config_path: Path | None,
) -> None:
    """Run a task defined in pt.toml.

    TASK_NAME is the name of the task to run.
    Additional ARGS are passed to the task's script/command.
    """
    if not check_uv_installed():
        print_uv_not_installed_error()
        sys.exit(1)

    runner = Runner.from_config_file(config_path, verbose=verbose, profile=profile)

    # Resolve alias to task name
    from pt.config import resolve_task_name
    try:
        resolved_task_name = resolve_task_name(runner.config, task_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    result = runner.run_task(resolved_task_name, list(args))

    sys.exit(result.return_code)


@main.command("exec")
@click.argument("script", type=click.Path(exists=True))
@click.argument("args", nargs=-1)
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.option(
    "-p",
    "--profile",
    "profile",
    shell_complete=complete_profile_name,
    help="Profile to use (dev, ci, prod, etc.)",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def exec_script(
    script: str, args: tuple[str, ...], verbose: bool, profile: str | None, config_path: Path | None
) -> None:
    """Run a Python script with pt context.

    SCRIPT is the path to the Python script to run.
    Additional ARGS are passed to the script.

    The script will inherit global environment variables and PYTHONPATH
    from pt.toml, and can use PEP 723 inline metadata for dependencies.
    """
    if not check_uv_installed():
        print_uv_not_installed_error()
        sys.exit(1)

    runner = Runner.from_config_file(config_path, verbose=verbose, profile=profile)
    result = runner.run_script(script, list(args))

    sys.exit(result.return_code)


@main.command()
@click.argument("task_names", nargs=-1, shell_complete=complete_task_name)
@click.option(
    "-t",
    "--tag",
    "tags",
    multiple=True,
    help="Run tasks with these tags (can be used multiple times)",
)
@click.option("--match-any", is_flag=True, help="Match ANY tag instead of ALL tags")
@click.option("--category", help="Run all tasks in this category")
@click.option("--parallel", is_flag=True, help="Run tasks in parallel")
@click.option("-s", "--sequential", is_flag=True, help="Run tasks sequentially (default)")
@click.option(
    "--on-failure",
    type=click.Choice(["fail-fast", "wait", "continue"]),
    default="fail-fast",
    help="Behavior when a task fails",
)
@click.option(
    "--output",
    type=click.Choice(["buffered", "interleaved"]),
    default="buffered",
    help="Output mode for parallel execution",
)
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.option(
    "-p",
    "--profile",
    "profile",
    shell_complete=complete_profile_name,
    help="Profile to use (dev, ci, prod, etc.)",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def multi(
    task_names: tuple[str, ...],
    tags: tuple[str, ...],
    match_any: bool,
    category: str | None,
    parallel: bool,
    sequential: bool,
    on_failure: str,
    output: str,
    verbose: bool,
    profile: str | None,
    config_path: Path | None,
) -> None:
    """Run multiple tasks.

    Specify TASK_NAMES directly, or use --tag/--category to filter tasks.
    """
    if not check_uv_installed():
        print_uv_not_installed_error()
        sys.exit(1)

    runner = Runner.from_config_file(config_path, verbose=verbose, profile=profile)

    # Determine which tasks to run
    if category:
        # Run tasks by category
        if task_names:
            console.print("[yellow]Warning:[/yellow] Task names are ignored when using --category")
        tasks_dict = runner.config.get_tasks_by_category(category)
        final_task_names = list(tasks_dict.keys())
        if not final_task_names:
            console.print(f"[yellow]No tasks found in category: {category}[/yellow]")
            sys.exit(0)
    elif tags:
        # Run tasks by tag
        if task_names:
            console.print("[yellow]Warning:[/yellow] Task names are ignored when using --tag")
        tasks_dict = runner.config.get_tasks_by_tags(list(tags), match_all=not match_any)
        final_task_names = list(tasks_dict.keys())
        if not final_task_names:
            console.print(f"[yellow]No tasks found with tag(s): {', '.join(tags)}[/yellow]")
            sys.exit(0)
    elif task_names:
        # Run tasks by name - resolve aliases
        from pt.config import resolve_task_name
        # Resolve all task names/aliases upfront
        try:
            final_task_names = [resolve_task_name(runner.config, name) for name in task_names]
        except ValueError as e:
            console.print(f"[red]Error:[/red] {e}")
            sys.exit(1)
    else:
        console.print("[red]Error:[/red] Either specify task names or use --tag")
        sys.exit(1)

    # Parse options
    is_parallel = parallel and not sequential
    failure_mode = OnFailure(on_failure)
    output_mode = OutputMode(output)

    results = runner.run_tasks(
        final_task_names,
        parallel=is_parallel,
        on_failure=failure_mode,
        output_mode=output_mode,
    )

    # Exit with error if any task failed
    failed = any(not r.success for r in results.values())
    sys.exit(1 if failed else 0)


@main.command()
@click.argument("pipeline_name", shell_complete=complete_pipeline_name)
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.option(
    "-p",
    "--profile",
    "profile",
    shell_complete=complete_profile_name,
    help="Profile to use (dev, ci, prod, etc.)",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def pipeline(
    pipeline_name: str, verbose: bool, profile: str | None, config_path: Path | None
) -> None:
    """Run a pipeline defined in pt.toml.

    PIPELINE_NAME is the name of the pipeline to run.
    """
    if not check_uv_installed():
        print_uv_not_installed_error()
        sys.exit(1)

    runner = Runner.from_config_file(config_path, verbose=verbose, profile=profile)
    results = runner.run_pipeline(pipeline_name)

    failed = any(not r.success for r in results.values())
    sys.exit(1 if failed else 0)


@main.command("list")
@click.option("-v", "--verbose", is_flag=True, help="Show task descriptions and dependencies")
@click.option("-a", "--all", "show_all", is_flag=True, help="Show private tasks (starting with _)")
@click.option(
    "-t", "--tag", "tags", multiple=True, help="Filter tasks by tag (can be used multiple times)"
)
@click.option("--match-any", is_flag=True, help="Match ANY tag instead of ALL tags")
@click.option("--category", help="Filter tasks by category")
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def list_tasks(
    verbose: bool,
    show_all: bool,
    tags: tuple[str, ...],
    match_any: bool,
    category: str | None,
    config_path: Path | None,
) -> None:
    """List available tasks and pipelines."""
    config, _ = load_config(config_path)

    # Filter by category first if specified
    if category:
        filtered_tasks = config.get_tasks_by_category(category)
    elif tags:
        # Filter tasks by tags if specified
        filtered_tasks = config.get_tasks_by_tags(list(tags), match_all=not match_any)
    else:
        filtered_tasks = config.tasks

    # Tasks table
    if filtered_tasks:
        table = Table(title="Tasks")
        table.add_column("Name", style="cyan")
        if verbose:
            table.add_column("Aliases", style="dim")
            table.add_column("Description")
            table.add_column("Category", style="yellow")
            table.add_column("Type")
            table.add_column("Dependencies")
            table.add_column("Tags", style="green")

        for name, task in sorted(filtered_tasks.items()):
            # Skip private tasks (starting with _) unless --all is specified
            if name.startswith("_") and not show_all:
                continue

            if verbose:
                task_type = "script" if task.script else "cmd" if task.cmd else "group"
                deps = (
                    ", ".join(d if isinstance(d, str) else d.task for d in task.depends_on) or "-"
                )
                aliases = ", ".join(task.aliases) if task.aliases else "-"
                category_str = task.category or "-"
                tags_str = ", ".join(task.tags) if task.tags else "-"
                table.add_row(
                    name, aliases, task.description or "-", category_str, task_type, deps, tags_str
                )
            else:
                # Show aliases inline in non-verbose mode
                display_name = name
                if task.aliases:
                    display_name = f"{name} ({', '.join(task.aliases)})"
                table.add_row(display_name)

        console.print(table)

    # Pipelines table
    if config.pipelines:
        console.print()
        table = Table(title="Pipelines")
        table.add_column("Name", style="magenta")
        if verbose:
            table.add_column("Description")
            table.add_column("Stages")

        for name, pipe in sorted(config.pipelines.items()):
            if verbose:
                stages_str = " -> ".join(
                    f"[{', '.join(s.tasks)}]{'*' if s.parallel else ''}" for s in pipe.stages
                )
                table.add_row(name, pipe.description or "-", stages_str)
            else:
                table.add_row(name)

        console.print(table)

    if not config.tasks and not config.pipelines:
        console.print("[yellow]No tasks or pipelines defined.[/yellow]")


@main.command("tags")
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def list_tags(config_path: Path | None) -> None:
    """List all tags used in tasks."""
    config, _ = load_config(config_path)

    all_tags = config.get_all_tags()

    if not all_tags:
        console.print("[yellow]No tags defined.[/yellow]")
        return

    table = Table(title="Tags")
    table.add_column("Tag", style="green")
    table.add_column("Count", style="cyan", justify="right")
    table.add_column("Tasks", style="dim")

    for tag in sorted(all_tags):
        tasks_with_tag = config.get_tasks_by_tag(tag)
        task_count = len(tasks_with_tag)
        task_names = ", ".join(sorted(tasks_with_tag.keys()))
        table.add_row(tag, str(task_count), task_names)

    console.print(table)


@main.command()
@click.argument("task_name", shell_complete=complete_task_name)
@click.argument("args", nargs=-1)
@click.option("--pattern", multiple=True, help="File patterns to watch (default: **/*.py)")
@click.option("-i", "--ignore", multiple=True, help="Patterns to ignore")
@click.option("--debounce", type=float, default=0.5, help="Debounce time in seconds")
@click.option("--no-clear", is_flag=True, help="Don't clear screen on changes")
@click.option("-v", "--verbose", is_flag=True, help="Show verbose output")
@click.option(
    "-p",
    "--profile",
    "profile",
    shell_complete=complete_profile_name,
    help="Profile to use (dev, ci, prod, etc.)",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def watch(
    task_name: str,
    args: tuple[str, ...],
    pattern: tuple[str, ...],
    ignore: tuple[str, ...],
    debounce: float,
    no_clear: bool,
    verbose: bool,
    profile: str | None,
    config_path: Path | None,
) -> None:
    """Watch for file changes and re-run a task.

    TASK_NAME is the name of the task to run when files change.
    Additional ARGS are passed to the task's script/command.
    """
    # Lazy import - only load watch module when needed
    from pt.watch import WatchConfig, watch_and_run_sync

    if not check_uv_installed():
        print_uv_not_installed_error()
        sys.exit(1)

    runner = Runner.from_config_file(config_path, verbose=verbose, profile=profile)

    watch_config = WatchConfig(
        patterns=list(pattern) if pattern else ["**/*.py"],
        ignore_patterns=list(ignore) if ignore else WatchConfig().ignore_patterns,
        debounce_seconds=debounce,
        clear_screen=not no_clear,
    )

    watch_and_run_sync(runner, task_name, list(args), watch_config, console)


@main.command()
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def check(config_path: Path | None) -> None:
    """Validate the pt configuration file."""
    config, path = load_config(config_path)

    console.print(f"[green]✓[/green] Configuration valid: {path}")
    console.print(f"  Project: {config.project.name or '(unnamed)'}")
    console.print(f"  Tasks: {len(config.tasks)}")
    console.print(f"  Pipelines: {len(config.pipelines)}")
    console.print(f"  Dependency groups: {len(config.dependencies)}")

    # Check for uv
    if check_uv_installed():
        console.print("[green]✓[/green] uv is installed")
    else:
        console.print("[yellow]![/yellow] uv is not installed")


@main.command()
@click.option("-f", "--force", is_flag=True, help="Overwrite existing config file")
@handle_errors
def init(force: bool) -> None:
    """Initialize a new pt.toml configuration file."""
    config_path = Path.cwd() / "pt.toml"

    if config_path.exists() and not force:
        console.print(f"[yellow]Config file already exists:[/yellow] {config_path}")
        console.print("[dim]Use --force to overwrite.[/dim]")
        sys.exit(1)

    template = """\
# pt configuration file
# See: https://github.com/your-repo/pt

[project]
name = ""
# python = "3.12"  # Default Python version
# default_profile = "dev"  # Profile to use when none specified

[env]
# Global environment variables
# PYTHONPATH = ["src"]

# env_files = [".env"]  # Load from .env files

[dependencies]
# Named dependency groups
# common = ["requests", "pydantic"]
# testing = ["pytest", "pytest-cov"]
# linting = ["ruff", "mypy"]

# [tasks.example]
# description = "An example task"
# script = "scripts/example.py"
# # Or use: cmd = "python -c 'print(1)'"
# dependencies = ["common"]
# env = { DEBUG = "1" }
# cwd = "."  # Working directory
# timeout = 300  # Timeout in seconds
# ignore_errors = false  # Continue on failure
# aliases = ["ex"]  # Alternative names: pt run ex

# [tasks.lint]
# description = "Run linting"
# cmd = "ruff check src/"
# dependencies = ["ruff"]
# aliases = ["l"]

# [tasks.test]
# description = "Run tests"
# cmd = "pytest"
# dependencies = ["testing"]
# pythonpath = ["src", "tests"]
# aliases = ["t"]

# [tasks.test-verbose]
# extend = "test"  # Inherit from test task
# description = "Run tests with verbose output"
# args = ["-v"]

# [tasks._setup]  # Private task (hidden from pt list)
# description = "Internal setup"
# cmd = "echo 'Setting up...'"

# [tasks.check]
# description = "Run all checks"
# depends_on = ["lint", "test"]
# parallel = true

# [tasks.deploy]
# description = "Deploy (only on Linux CI)"
# script = "scripts/deploy.py"
# condition = { platforms = ["linux"], env_set = ["CI"] }

# [profiles.dev]
# env = { DEBUG = "1", LOG_LEVEL = "debug" }
# env_files = [".env.dev"]

# [profiles.ci]
# env = { CI = "1" }

# [profiles.prod]
# env = { LOG_LEVEL = "warning" }
# python = "3.11"

# [pipelines.ci]
# description = "CI pipeline"
# on_failure = "fail-fast"  # or "wait", "continue"
# output = "buffered"  # or "interleaved"
# stages = [
#     { tasks = ["lint"], parallel = false },
#     { tasks = ["test"], parallel = false },
# ]
"""

    config_path.write_text(template)
    console.print(f"[green]✓[/green] Created {config_path}")
    console.print("\n[dim]Edit the file to add your tasks, then run:[/dim]")
    console.print("  pt list        # List available tasks")
    console.print("  pt run <task>  # Run a task")


if __name__ == "__main__":
    main()

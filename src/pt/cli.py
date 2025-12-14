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
from pt.executor import ExecutionResult, check_uv_installed
from pt.models import OnFailure, OutputMode, PtConfig
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
    console.print(
        '  • Windows:     [cyan]powershell -c "irm https://astral.sh/uv/install.ps1 | iex"[/cyan]'
    )
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


def _run_inline_task(
    inline_command: str,
    args: list[str],
    env_vars: list[str],
    working_dir: Path | None,
    timeout: int | None,
    python_version: str | None,
    verbose: bool,
    profile: str | None,
    config_path: Path | None,
) -> ExecutionResult:
    """Execute an inline task defined on the command line.

    Args:
        inline_command: The command to execute
        args: Additional arguments to pass
        env_vars: Environment variables (KEY=VALUE format)
        working_dir: Working directory
        timeout: Timeout in seconds
        python_version: Python version
        verbose: Verbose output
        profile: Profile name
        config_path: Config file path (for settings)

    Returns:
        ExecutionResult from execution
    """
    from pt.config import (
        ConfigNotFoundError,
        build_profile_env,
        get_effective_runner,
        get_project_root,
        load_config,
    )
    from pt.executor import UvCommand, execute_sync
    from pt.models import TaskConfig

    # Parse environment variables
    parsed_env: dict[str, str] = {}
    for env_var in env_vars:
        if "=" not in env_var:
            console.print(f"[red]Error:[/red] Invalid env format: {env_var} (expected KEY=VALUE)")
            sys.exit(1)
        key, value = env_var.split("=", 1)
        parsed_env[key] = value

    # Try to load config if it exists (for settings/profile support)
    config = None
    project_root = Path.cwd()
    runner_prefix = None

    try:
        if config_path:
            config, path = load_config(config_path)
            project_root = get_project_root(path)
        else:
            # Try to find config but don't fail if not found
            try:
                config, path = load_config(None)
                project_root = get_project_root(path)
            except ConfigNotFoundError:
                pass  # No config file, use defaults
    except Exception:
        pass  # Ignore config errors for inline tasks

    # Build environment
    final_env: dict[str, str] = {}

    if config:
        # Merge global/profile env if config exists
        final_env = build_profile_env(config, project_root, profile)

        # Get runner prefix from config
        # Create a temporary TaskConfig to use with get_effective_runner
        temp_task = TaskConfig(cmd=inline_command)
        runner_prefix = get_effective_runner(config, temp_task, profile)

    # Override with inline env vars
    final_env.update(parsed_env)

    # Determine working directory
    cwd = working_dir if working_dir else project_root

    # Determine Python version
    effective_python = python_version
    if not effective_python and config:
        from pt.config import get_profile_python

        effective_python = get_profile_python(config, profile)

    # Build command
    command = UvCommand(
        cmd=inline_command,
        args=args,
        env=final_env,
        cwd=cwd,
        python=effective_python,
        runner=runner_prefix,
    )

    if verbose:
        console.print(f"[dim]Running inline: {' '.join(command.build())}[/dim]")

    # Execute
    result = execute_sync(command, capture_output=not verbose, timeout=timeout)

    if verbose or not result.success:
        from pt.parallel import print_task_output

        print_task_output("inline", result, console)

    return result


@click.group()
@click.version_option(version=__version__, prog_name="pt")
def main() -> None:
    """pt - A Python task runner for Python scripts using uv."""
    pass


@main.command()
@click.argument("task_name", required=False, shell_complete=complete_task_name)
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
@click.option(
    "--inline",
    "inline_command",
    help="Define task inline without config file",
)
@click.option(
    "--env",
    "env_vars",
    multiple=True,
    help="Environment variables (KEY=VALUE, can be used multiple times)",
)
@click.option(
    "--cwd",
    "working_dir",
    type=click.Path(exists=True, path_type=Path),
    help="Working directory for inline task",
)
@click.option(
    "--timeout",
    type=int,
    help="Timeout in seconds for inline task",
)
@click.option(
    "--python",
    "python_version",
    help="Python version for inline task",
)
@handle_errors
def run(
    task_name: str | None,
    args: tuple[str, ...],
    verbose: bool,
    profile: str | None,
    config_path: Path | None,
    inline_command: str | None,
    env_vars: tuple[str, ...],
    working_dir: Path | None,
    timeout: int | None,
    python_version: str | None,
) -> None:
    """Run a task defined in pt.toml or inline.

    TASK_NAME is the name of the task to run (not needed with --inline).
    Additional ARGS are passed to the task's script/command.

    Examples:
        pt run test                                    # Run configured task
        pt run --inline "pytest tests/"                # Inline command
        pt run --inline "python script.py" --env DEBUG=1  # With env vars
    """
    if not check_uv_installed():
        print_uv_not_installed_error()
        sys.exit(1)

    # Handle inline task
    if inline_command:
        if task_name:
            console.print("[yellow]Warning:[/yellow] Task name is ignored with --inline")
        result = _run_inline_task(
            inline_command=inline_command,
            args=list(args),
            env_vars=list(env_vars),
            working_dir=working_dir,
            timeout=timeout,
            python_version=python_version,
            verbose=verbose,
            profile=profile,
            config_path=config_path,
        )
        sys.exit(result.return_code)

    # Normal configured task execution
    if not task_name:
        console.print("[red]Error:[/red] TASK_NAME is required without --inline")
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
@click.argument("task_name", shell_complete=complete_task_name)
@click.option(
    "-p",
    "--profile",
    "profile",
    shell_complete=complete_profile_name,
    help="Profile to use (affects variable resolution)",
)
@click.option(
    "-c",
    "--config",
    "config_path",
    type=click.Path(exists=True, path_type=Path),
    help="Path to config file",
)
@handle_errors
def explain(task_name: str, profile: str | None, config_path: Path | None) -> None:
    """Show detailed information about a task.

    Displays the resolved task configuration including inheritance chain,
    environment variables, dependencies, and effective command.
    """
    from pt.config import (
        apply_variable_interpolation,
        build_profile_env,
        get_effective_profile,
        get_effective_runner,
        get_profile_python,
        get_project_root,
        resolve_task_name,
    )

    # Load config with variable interpolation
    config, path = load_config(config_path)
    project_root = get_project_root(path)

    effective_profile = get_effective_profile(config, profile)
    config = apply_variable_interpolation(config, effective_profile)

    # Resolve alias to task name
    try:
        resolved_name = resolve_task_name(config, task_name)
    except ValueError as e:
        console.print(f"[red]Error:[/red] {e}")
        sys.exit(1)

    task = config.get_task(resolved_name)

    # Get the original (pre-inheritance) task for showing inheritance chain
    raw_config = _load_raw_config(path)
    inheritance_chain = _get_inheritance_chain(raw_config, resolved_name)

    # Header
    console.print(f"\n[bold cyan]Task:[/bold cyan] {resolved_name}")
    if resolved_name != task_name:
        console.print(f"[dim](alias for: {task_name})[/dim]")

    # Description
    if task.description:
        console.print(f"[bold]Description:[/bold] {task.description}")

    # Source info
    console.print(f"[bold]Config:[/bold] {path}")

    # Inheritance chain
    if len(inheritance_chain) > 1:
        chain_str = " → ".join(inheritance_chain)
        console.print(f"[bold]Inheritance:[/bold] {chain_str}")

    # Task type and command
    console.print()
    if task.script:
        console.print("[bold]Type:[/bold] script")
        console.print(f"[bold]Script:[/bold] {task.script}")
    elif task.cmd:
        console.print("[bold]Type:[/bold] command")
        console.print(f"[bold]Command:[/bold] {task.cmd}")
    else:
        console.print("[bold]Type:[/bold] group (depends_on only)")

    # Args
    if task.args:
        console.print(f"[bold]Args:[/bold] {' '.join(task.args)}")

    # Runner prefix
    runner = get_effective_runner(config, task, effective_profile)
    if runner:
        console.print(f"[bold]Runner prefix:[/bold] {runner}")

    # Working directory
    if task.cwd:
        console.print(f"[bold]Working directory:[/bold] {task.cwd}")

    # Python version
    python_version = task.python or get_profile_python(config, effective_profile)
    if python_version:
        console.print(f"[bold]Python:[/bold] {python_version}")

    # Timeout
    if task.timeout:
        console.print(f"[bold]Timeout:[/bold] {task.timeout}s")

    # Package dependencies
    if task.dependencies:
        resolved_deps = config.resolve_dependencies(task)
        console.print("[bold]Package dependencies:[/bold]")
        for dep in resolved_deps:
            console.print(f"  • {dep}")

    # Task dependencies (depends_on)
    if task.depends_on:
        console.print("[bold]Task dependencies:[/bold]")
        for task_dep in task.depends_on:
            if isinstance(task_dep, str):
                console.print(f"  • {task_dep}")
            else:
                args_str = f" (args: {' '.join(task_dep.args)})" if task_dep.args else ""
                console.print(f"  • {task_dep.task}{args_str}")

    # Environment variables
    console.print()
    console.print("[bold]Environment:[/bold]")

    # Build full environment
    profile_env = build_profile_env(config, project_root, effective_profile)
    task_env = {**profile_env, **task.env}

    if task_env:
        for key, value in sorted(task_env.items()):
            # Truncate long values
            display_value = value if len(value) <= 60 else f"{value[:57]}..."
            console.print(f"  {key}={display_value}")
    else:
        console.print("  [dim](none)[/dim]")

    # PYTHONPATH
    if task.pythonpath:
        console.print("[bold]PYTHONPATH:[/bold]")
        for p in task.pythonpath:
            console.print(f"  • {p}")

    # Conditions
    if task.condition or task.condition_script:
        console.print()
        console.print("[bold]Conditions:[/bold]")
        if task.condition:
            cond = task.condition
            if cond.platforms:
                console.print(f"  platforms: {', '.join(cond.platforms)}")
            if cond.python_version:
                console.print(f"  python_version: {cond.python_version}")
            if cond.env_set:
                console.print(f"  env_set: {', '.join(cond.env_set)}")
            if cond.env_not_set:
                console.print(f"  env_not_set: {', '.join(cond.env_not_set)}")
            if cond.env_true:
                console.print(f"  env_true: {', '.join(cond.env_true)}")
            if cond.env_false:
                console.print(f"  env_false: {', '.join(cond.env_false)}")
            if cond.env_equals:
                for k, v in cond.env_equals.items():
                    console.print(f"  env_equals: {k}={v}")
            if cond.files_exist:
                console.print(f"  files_exist: {', '.join(cond.files_exist)}")
            if cond.files_not_exist:
                console.print(f"  files_not_exist: {', '.join(cond.files_not_exist)}")
        if task.condition_script:
            console.print(f"  condition_script: {task.condition_script}")

    # Hooks
    hooks = [
        ("before_task", task.before_task),
        ("after_success", task.after_success),
        ("after_failure", task.after_failure),
        ("after_task", task.after_task),
    ]
    active_hooks = [(name, script) for name, script in hooks if script]
    if active_hooks:
        console.print()
        console.print("[bold]Hooks:[/bold]")
        for name, script in active_hooks:
            console.print(f"  {name}: {script}")

    # Tags and category
    if task.tags or task.category:
        console.print()
        if task.category:
            console.print(f"[bold]Category:[/bold] {task.category}")
        if task.tags:
            console.print(f"[bold]Tags:[/bold] {', '.join(task.tags)}")

    # Aliases
    if task.aliases:
        console.print(f"[bold]Aliases:[/bold] {', '.join(task.aliases)}")

    # Options
    options = []
    if task.ignore_errors:
        options.append("ignore_errors")
    if task.parallel:
        options.append("parallel")
    if task.disable_runner:
        options.append("disable_runner")
    if task.use_vars:
        options.append("use_vars")
    if options:
        console.print(f"[bold]Options:[/bold] {', '.join(options)}")

    # Output redirection
    if task.stdout or task.stderr:
        console.print()
        console.print("[bold]Output redirection:[/bold]")
        if task.stdout:
            console.print(f"  stdout: {task.stdout}")
        if task.stderr:
            console.print(f"  stderr: {task.stderr}")

    console.print()


def _load_raw_config(config_path: Path) -> PtConfig:
    """Load config without resolving inheritance (for showing inheritance chain)."""
    import sys

    if sys.version_info >= (3, 11):
        import tomllib
    else:
        import tomli as tomllib

    with config_path.open("rb") as f:
        raw_data = tomllib.load(f)

    # Extract pt config from pyproject.toml if needed
    if config_path.name == "pyproject.toml":
        pt_data = raw_data.get("tool", {}).get("pt", raw_data.get("tool", {}).get("pyr", {}))
    else:
        pt_data = raw_data

    return PtConfig.model_validate(pt_data)


def _get_inheritance_chain(config: PtConfig, task_name: str) -> list[str]:
    """Get the inheritance chain for a task (from child to root ancestor)."""
    chain = [task_name]
    current = task_name

    while current in config.tasks:
        task = config.tasks[current]
        if task.extend:
            chain.append(task.extend)
            current = task.extend
        else:
            break

    return chain


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
    """Validate the pt configuration file.

    Performs comprehensive validation including:
    - TOML syntax and schema validation
    - Task reference validation (depends_on, extend)
    - Profile and pipeline reference validation
    - Best practice warnings (missing descriptions, timeouts)
    """
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

    # Run enhanced validation
    warnings = _validate_config(config)
    errors = [w for w in warnings if w.startswith("[error]")]
    warns = [w for w in warnings if w.startswith("[warn]")]

    if errors:
        console.print()
        console.print("[red]Errors:[/red]")
        for error in errors:
            console.print(f"  {error.replace('[error] ', '')}")

    if warns:
        console.print()
        console.print("[yellow]Warnings:[/yellow]")
        for warn in warns:
            console.print(f"  {warn.replace('[warn] ', '')}")

    if not errors and not warns:
        console.print("[green]✓[/green] No issues found")
    elif errors:
        sys.exit(1)


def _validate_config(config: PtConfig) -> list[str]:
    """Perform enhanced validation of the configuration.

    Returns a list of warning/error messages.
    """
    from pt.config import resolve_task_name

    issues: list[str] = []

    # Validate task references in depends_on
    for task_name, task in config.tasks.items():
        for dep in task.depends_on:
            dep_name = dep if isinstance(dep, str) else dep.task
            try:
                resolve_task_name(config, dep_name)
            except ValueError:
                issues.append(
                    f"[error] Task '{task_name}' depends on unknown task '{dep_name}'"
                )

    # Validate extend references (already checked during load, but double-check)
    raw_tasks = config.tasks
    for task_name, task in raw_tasks.items():
        if task.extend and task.extend not in raw_tasks:
            issues.append(
                f"[error] Task '{task_name}' extends unknown task '{task.extend}'"
            )

    # Validate pipeline task references
    # Build set of valid task names and aliases for O(1) lookup
    valid_task_refs = set(config.tasks.keys())
    for task in config.tasks.values():
        valid_task_refs.update(task.aliases)

    for pipeline_name, pipeline in config.pipelines.items():
        for i, stage in enumerate(pipeline.stages):
            invalid_tasks = [
                f"[error] Pipeline '{pipeline_name}' stage {i + 1} references "
                f"unknown task '{stage_task}'"
                for stage_task in stage.tasks
                if stage_task not in valid_task_refs
            ]
            issues.extend(invalid_tasks)

    # Validate default_profile exists
    if config.project.default_profile and config.project.default_profile not in config.profiles:
        issues.append(
            f"[error] default_profile '{config.project.default_profile}' not found in profiles"
        )

    # Validate on_error_task exists
    if config.project.on_error_task:
        try:
            resolve_task_name(config, config.project.on_error_task)
        except ValueError:
            issues.append(
                f"[error] on_error_task '{config.project.on_error_task}' not found"
            )

    # Validate dependency group references
    for task in config.tasks.values():
        for dep in task.dependencies:
            # Check if it's a group reference (exists in config.dependencies)
            # or a direct package (which is also valid)
            # We only warn if it looks like a group name but doesn't exist
            if dep in config.dependencies:
                continue  # Valid group reference
            # Check if it looks like a package (has version specifier or is lowercase with hyphens)
            if any(c in dep for c in ">=<!=@"):
                continue  # Looks like a package with version
            # Could be a simple package name - that's fine too

    # Best practice warnings
    for task_name, task in config.tasks.items():
        # Skip private tasks for some warnings
        is_private = task_name.startswith("_")

        # Warning: No description on public tasks
        if not is_private and not task.description:
            issues.append(f"[warn] Task '{task_name}' has no description")

    # Warning: Unused dependency groups
    used_groups: set[str] = set()
    for task in config.tasks.values():
        for dep in task.dependencies:
            if dep in config.dependencies:
                used_groups.add(dep)

    unused_groups = set(config.dependencies.keys()) - used_groups
    if unused_groups:
        issues.append(
            f"[warn] Unused dependency groups: {', '.join(sorted(unused_groups))}"
        )

    # Warning: Variables defined but use_vars not enabled
    if config.variables and not config.project.use_vars:
        # Check if any task has use_vars enabled
        any_task_uses_vars = any(t.use_vars for t in config.tasks.values())
        if not any_task_uses_vars:
            issues.append(
                "[warn] Variables defined but use_vars is not enabled globally or on any task"
            )

    return issues


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

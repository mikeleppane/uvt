"""File watching for automatic task re-execution."""

from __future__ import annotations

import asyncio
import contextlib
import fnmatch
import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

    from uvr.runner import Runner

from rich.console import Console


@dataclass
class WatchConfig:
    """Configuration for file watching."""

    patterns: list[str] = field(default_factory=lambda: ["**/*.py"])
    ignore_patterns: list[str] = field(
        default_factory=lambda: [
            "**/__pycache__/**",
            "**/.git/**",
            "**/.venv/**",
            "**/venv/**",
            "**/*.pyc",
            "**/node_modules/**",
            "**/.mypy_cache/**",
            "**/.pytest_cache/**",
            "**/.ruff_cache/**",
        ]
    )
    debounce_seconds: float = 0.5
    clear_screen: bool = True


def _match_patterns(path: Path, patterns: list[str], root: Path) -> bool:
    """Check if a path matches any of the given glob patterns."""
    rel_path = str(path.relative_to(root))
    for pattern in patterns:
        if fnmatch.fnmatch(rel_path, pattern):
            return True
        if fnmatch.fnmatch(path.name, pattern):
            return True
    return False


def _get_file_mtimes(
    root: Path,
    patterns: list[str],
    ignore_patterns: list[str],
) -> dict[Path, float]:
    """Get modification times for all matching files."""
    mtimes: dict[Path, float] = {}

    for pattern in patterns:
        # Handle ** patterns
        if "**" in pattern:
            for path in root.rglob(pattern.replace("**/", "")):
                if path.is_file() and not _match_patterns(path, ignore_patterns, root):
                    with contextlib.suppress(OSError):
                        mtimes[path] = path.stat().st_mtime
        else:
            for path in root.glob(pattern):
                if path.is_file() and not _match_patterns(path, ignore_patterns, root):
                    with contextlib.suppress(OSError):
                        mtimes[path] = path.stat().st_mtime

    return mtimes


def _find_changes(
    old_mtimes: dict[Path, float],
    new_mtimes: dict[Path, float],
) -> tuple[list[Path], list[Path], list[Path]]:
    """Find added, modified, and deleted files.

    Returns:
        Tuple of (added, modified, deleted) file lists.
    """
    old_files = set(old_mtimes.keys())
    new_files = set(new_mtimes.keys())

    added = list(new_files - old_files)
    deleted = list(old_files - new_files)
    modified = [path for path in old_files & new_files if old_mtimes[path] != new_mtimes[path]]

    return added, modified, deleted


async def watch_and_run(
    runner: Runner,
    task_name: str,
    extra_args: list[str] | None = None,
    config: WatchConfig | None = None,
    console: Console | None = None,
) -> None:
    """Watch for file changes and re-run a task.

    Args:
        runner: The Runner instance to use.
        task_name: Name of the task to run.
        extra_args: Additional arguments to pass to the task.
        config: Watch configuration.
        console: Console for output.
    """
    if config is None:
        config = WatchConfig()
    if console is None:
        console = Console()

    root = runner.project_root
    console.print(f"[cyan]Watching for changes in {root}[/cyan]")
    console.print(f"[dim]Patterns: {config.patterns}[/dim]")
    console.print("[dim]Press Ctrl+C to stop[/dim]\n")

    # Initial run
    if config.clear_screen:
        console.clear()
    console.print(f"[bold green]Running {task_name}...[/bold green]\n")
    runner.run_task(task_name, extra_args)

    # Get initial file state
    mtimes = _get_file_mtimes(root, config.patterns, config.ignore_patterns)
    last_run = time.time()

    try:
        while True:
            await asyncio.sleep(0.1)

            # Check for changes
            new_mtimes = _get_file_mtimes(root, config.patterns, config.ignore_patterns)
            added, modified, deleted = _find_changes(mtimes, new_mtimes)

            if added or modified or deleted:
                # Debounce
                now = time.time()
                if now - last_run < config.debounce_seconds:
                    mtimes = new_mtimes
                    continue

                # Show what changed
                if config.clear_screen:
                    console.clear()

                console.print("\n[yellow]Changes detected:[/yellow]")
                for path in added[:5]:
                    console.print(f"  [green]+ {path.relative_to(root)}[/green]")
                for path in modified[:5]:
                    console.print(f"  [yellow]~ {path.relative_to(root)}[/yellow]")
                for path in deleted[:5]:
                    console.print(f"  [red]- {path.relative_to(root)}[/red]")

                total_changes = len(added) + len(modified) + len(deleted)
                if total_changes > 15:
                    console.print(f"  [dim]... and {total_changes - 15} more[/dim]")

                console.print(f"\n[bold green]Running {task_name}...[/bold green]\n")

                # Run the task
                runner.run_task(task_name, extra_args)

                # Update state
                mtimes = new_mtimes
                last_run = time.time()

    except KeyboardInterrupt:
        console.print("\n[yellow]Watch stopped[/yellow]")


def watch_and_run_sync(
    runner: Runner,
    task_name: str,
    extra_args: list[str] | None = None,
    config: WatchConfig | None = None,
    console: Console | None = None,
) -> None:
    """Synchronous wrapper for watch_and_run."""
    asyncio.run(watch_and_run(runner, task_name, extra_args, config, console))

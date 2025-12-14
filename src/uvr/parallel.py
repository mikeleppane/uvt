"""Async parallel task execution with configurable failure handling."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Protocol

from rich.console import Console
from rich.panel import Panel
from rich.progress import BarColumn, Progress, SpinnerColumn, TaskID, TextColumn
from rich.table import Table

from uvr.models import OnFailure, OutputMode

if TYPE_CHECKING:
    from collections.abc import Coroutine
    from typing import Any

    from uvr.executor import ExecutionResult


class TaskExecutor(Protocol):
    """Protocol for task execution functions."""

    def __call__(
        self,
        task_name: str,
        output_queue: asyncio.Queue[tuple[str, str]] | None,
    ) -> Coroutine[Any, Any, ExecutionResult]: ...


@dataclass
class TaskStatus:
    """Status of a task during execution."""

    name: str
    status: str = "pending"  # pending, running, success, failed
    result: ExecutionResult | None = None


@dataclass
class ParallelExecutor:
    """Execute multiple tasks in parallel with configurable behavior."""

    on_failure: OnFailure = OnFailure.FAIL_FAST
    output_mode: OutputMode = OutputMode.BUFFERED
    console: Console = field(default_factory=Console)

    async def execute(
        self,
        task_names: list[str],
        executor: TaskExecutor,
    ) -> dict[str, ExecutionResult]:
        """Execute tasks in parallel.

        Args:
            task_names: Names of tasks to execute.
            executor: Async function to execute each task.

        Returns:
            Dict mapping task names to their results.
        """
        if not task_names:
            return {}

        results: dict[str, ExecutionResult] = {}
        statuses = {name: TaskStatus(name=name) for name in task_names}
        output_queue: asyncio.Queue[tuple[str, str]] = asyncio.Queue()
        cancel_event = asyncio.Event()

        async def run_task(name: str) -> None:
            # Check cancel BEFORE starting
            if cancel_event.is_set():
                statuses[name].status = "skipped"
                return

            statuses[name].status = "running"

            queue = output_queue if self.output_mode == OutputMode.INTERLEAVED else None
            result = await executor(name, queue)

            # Don't store result if cancelled during execution
            if cancel_event.is_set() and not result.success:
                statuses[name].status = "cancelled"
                return

            statuses[name].result = result
            results[name] = result

            if result.success:
                statuses[name].status = "success"
            else:
                statuses[name].status = "failed"
                if self.on_failure == OnFailure.FAIL_FAST:
                    cancel_event.set()

        # Create tasks
        tasks = [asyncio.create_task(run_task(name)) for name in task_names]

        # Handle output display
        if self.output_mode == OutputMode.INTERLEAVED:
            output_task = asyncio.create_task(self._display_interleaved(output_queue, statuses))
            task_results = await asyncio.gather(*tasks, return_exceptions=True)
            # Log any unexpected exceptions from tasks
            for task_name, result in zip(task_names, task_results, strict=True):
                if isinstance(result, Exception):
                    self.console.print(f"[red]Task {task_name} raised exception: {result}[/red]")
            await output_queue.put(("__done__", ""))
            await output_task
        else:
            # Buffered mode with progress display
            await self._run_with_progress(tasks, statuses)

        # Cancel remaining tasks if fail-fast triggered
        if cancel_event.is_set() and self.on_failure == OnFailure.FAIL_FAST:
            for task in tasks:
                if not task.done():
                    task.cancel()

        return results

    async def _run_with_progress(
        self,
        tasks: list[asyncio.Task[None]],
        statuses: dict[str, TaskStatus],
    ) -> None:
        """Run tasks with a progress display."""
        progress = Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            console=self.console,
        )

        task_ids: dict[str, TaskID] = {}
        with progress:
            for name in statuses:
                task_ids[name] = progress.add_task(f"[cyan]{name}", total=1)

            while not all(t.done() for t in tasks):
                for name, status in statuses.items():
                    if status.status == "running":
                        progress.update(task_ids[name], description=f"[yellow]{name}...")
                    elif status.status == "success":
                        progress.update(task_ids[name], description=f"[green]{name} ✓", completed=1)
                    elif status.status == "failed":
                        progress.update(task_ids[name], description=f"[red]{name} ✗", completed=1)

                await asyncio.sleep(0.1)

            # Final update
            for name, status in statuses.items():
                if status.status == "success":
                    progress.update(task_ids[name], description=f"[green]{name} ✓", completed=1)
                elif status.status == "failed":
                    progress.update(task_ids[name], description=f"[red]{name} ✗", completed=1)

    async def _display_interleaved(
        self,
        queue: asyncio.Queue[tuple[str, str]],
        statuses: dict[str, TaskStatus],  # noqa: ARG002
    ) -> None:
        """Display interleaved output from multiple tasks."""
        while True:
            task_name, line = await queue.get()
            if task_name == "__done__":
                break
            self.console.print(line, end="")


@dataclass
class SequentialExecutor:
    """Execute tasks sequentially."""

    console: Console = field(default_factory=Console)

    async def execute(
        self,
        task_names: list[str],
        executor: TaskExecutor,
    ) -> dict[str, ExecutionResult]:
        """Execute tasks one by one.

        Args:
            task_names: Names of tasks to execute in order.
            executor: Async function to execute each task.

        Returns:
            Dict mapping task names to their results.
        """
        results: dict[str, ExecutionResult] = {}

        for name in task_names:
            self.console.print(f"[cyan]Running:[/cyan] {name}")
            result = await executor(name, None)
            results[name] = result

            if result.success:
                self.console.print(f"[green]✓[/green] {name}")
            else:
                self.console.print(f"[red]✗[/red] {name}")
                if result.stderr:
                    self.console.print(result.stderr, style="red")
                break

        return results


def print_results_summary(
    results: dict[str, ExecutionResult],
    console: Console | None = None,
) -> None:
    """Print a summary table of task results."""
    if console is None:
        console = Console()

    table = Table(title="Task Results")
    table.add_column("Task", style="cyan")
    table.add_column("Status")
    table.add_column("Exit Code", justify="right")

    for name, result in results.items():
        status = "[green]✓ Success[/green]" if result.success else "[red]✗ Failed[/red]"
        table.add_row(name, status, str(result.return_code))

    console.print(table)


def print_task_output(
    name: str,
    result: ExecutionResult,
    console: Console | None = None,
) -> None:
    """Print detailed output from a task."""
    if console is None:
        console = Console()

    if result.stdout:
        console.print(Panel(result.stdout.strip(), title=f"{name} stdout", border_style="blue"))

    if result.stderr:
        console.print(Panel(result.stderr.strip(), title=f"{name} stderr", border_style="red"))

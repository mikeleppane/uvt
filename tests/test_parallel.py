"""Tests for parallel task execution."""

from __future__ import annotations

import asyncio

import pytest
from rich.console import Console

from uvr.executor import ExecutionResult, OutputMode
from uvr.models import OnFailure
from uvr.parallel import (
    ParallelExecutor,
    SequentialExecutor,
    TaskStatus,
    print_results_summary,
    print_task_output,
)


class TestTaskStatus:
    """Tests for TaskStatus dataclass."""

    def test_default_status(self) -> None:
        """Test TaskStatus default values."""
        status = TaskStatus(name="test")
        assert status.name == "test"
        assert status.status == "pending"
        assert status.result is None

    def test_with_result(self) -> None:
        """Test TaskStatus with execution result."""
        result = ExecutionResult(
            return_code=0,
            stdout="output",
            stderr="",
            command=["echo", "test"],
        )
        status = TaskStatus(name="test", status="success", result=result)
        assert status.name == "test"
        assert status.status == "success"
        assert status.result == result


class TestParallelExecutor:
    """Tests for ParallelExecutor."""

    @pytest.mark.asyncio
    async def test_execute_empty_tasks(self) -> None:
        """Test executing empty task list."""
        executor = ParallelExecutor()

        async def mock_executor(
            task_name: str,  # noqa: ARG001
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            msg = "Should not be called"
            raise RuntimeError(msg)

        results = await executor.execute([], mock_executor)
        assert results == {}

    @pytest.mark.asyncio
    async def test_execute_single_task_success(self) -> None:
        """Test executing single successful task."""
        executor = ParallelExecutor()

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            return ExecutionResult(
                return_code=0,
                stdout=f"output from {task_name}",
                stderr="",
                command=["test"],
            )

        results = await executor.execute(["task1"], mock_executor)
        assert len(results) == 1
        assert "task1" in results
        assert results["task1"].success
        assert "output from task1" in results["task1"].stdout

    @pytest.mark.asyncio
    async def test_execute_multiple_tasks_success(self) -> None:
        """Test executing multiple successful tasks in parallel."""
        executor = ParallelExecutor()

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            await asyncio.sleep(0.01)  # Simulate work
            return ExecutionResult(
                return_code=0,
                stdout=f"output from {task_name}",
                stderr="",
                command=["test"],
            )

        results = await executor.execute(["task1", "task2", "task3"], mock_executor)
        assert len(results) == 3
        assert all(results[f"task{i}"].success for i in range(1, 4))

    @pytest.mark.asyncio
    async def test_execute_with_failure_fail_fast(self) -> None:
        """Test fail-fast behavior when a task fails."""
        executor = ParallelExecutor(on_failure=OnFailure.FAIL_FAST)

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            if task_name == "task2":
                await asyncio.sleep(0.01)
                return ExecutionResult(return_code=1, stdout="", stderr="error", command=["test"])
            # Other tasks sleep longer to simulate being cancelled
            await asyncio.sleep(0.5)
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["task1", "task2", "task3"], mock_executor)

        # task2 should fail, others might be skipped/cancelled
        assert "task2" in results
        assert not results["task2"].success

    @pytest.mark.asyncio
    async def test_execute_with_failure_wait(self) -> None:
        """Test wait behavior when a task fails."""
        executor = ParallelExecutor(on_failure=OnFailure.WAIT)

        call_count = {"count": 0}

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            call_count["count"] += 1
            await asyncio.sleep(0.01)
            if task_name == "task2":
                return ExecutionResult(return_code=1, stdout="", stderr="error", command=["test"])
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["task1", "task2", "task3"], mock_executor)

        # All tasks should be executed with WAIT mode
        assert call_count["count"] == 3
        assert "task2" in results
        assert not results["task2"].success

    @pytest.mark.asyncio
    async def test_execute_with_failure_continue(self) -> None:
        """Test continue behavior when tasks fail."""
        executor = ParallelExecutor(on_failure=OnFailure.CONTINUE)

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            await asyncio.sleep(0.01)
            # Make task2 and task3 fail
            if task_name in ("task2", "task3"):
                return ExecutionResult(return_code=1, stdout="", stderr="error", command=["test"])
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["task1", "task2", "task3", "task4"], mock_executor)

        # All tasks should complete
        assert len(results) == 4
        assert results["task1"].success
        assert not results["task2"].success
        assert not results["task3"].success
        assert results["task4"].success

    @pytest.mark.asyncio
    async def test_execute_interleaved_output(self) -> None:
        """Test interleaved output mode."""
        executor = ParallelExecutor(output_mode=OutputMode.INTERLEAVED)

        async def mock_executor(
            task_name: str, output_queue: asyncio.Queue[tuple[str, str]] | None
        ) -> ExecutionResult:
            if output_queue:
                await output_queue.put((task_name, f"output from {task_name}\n"))
            await asyncio.sleep(0.01)
            return ExecutionResult(return_code=0, stdout="", stderr="", command=["test"])

        results = await executor.execute(["task1", "task2"], mock_executor)
        assert len(results) == 2
        assert all(r.success for r in results.values())

    @pytest.mark.asyncio
    async def test_execute_buffered_output(self) -> None:
        """Test buffered output mode."""
        executor = ParallelExecutor(output_mode=OutputMode.BUFFERED)

        async def mock_executor(
            task_name: str, output_queue: asyncio.Queue[tuple[str, str]] | None
        ) -> ExecutionResult:
            # Queue should be None in buffered mode
            assert output_queue is None
            await asyncio.sleep(0.01)
            return ExecutionResult(
                return_code=0,
                stdout=f"output from {task_name}",
                stderr="",
                command=["test"],
            )

        results = await executor.execute(["task1", "task2"], mock_executor)
        assert len(results) == 2
        assert results["task1"].stdout == "output from task1"
        assert results["task2"].stdout == "output from task2"

    @pytest.mark.asyncio
    async def test_cancel_pending_tasks_on_failure(self) -> None:
        """Test that pending tasks are cancelled on fail-fast."""
        executor = ParallelExecutor(on_failure=OnFailure.FAIL_FAST)

        started_tasks: list[str] = []

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            started_tasks.append(task_name)
            if task_name == "fail":
                return ExecutionResult(return_code=1, stdout="", stderr="error", command=["test"])
            await asyncio.sleep(1.0)  # Long sleep to test cancellation
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["fail", "task1", "task2"], mock_executor)

        # Only the failing task should complete
        assert "fail" in results
        assert not results["fail"].success
        # Other tasks might have started but should not complete
        assert len(results) <= 3


class TestSequentialExecutor:
    """Tests for SequentialExecutor."""

    @pytest.mark.asyncio
    async def test_execute_empty_tasks(self) -> None:
        """Test executing empty task list."""
        executor = SequentialExecutor()

        async def mock_executor(
            task_name: str,  # noqa: ARG001
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            msg = "Should not be called"
            raise RuntimeError(msg)

        results = await executor.execute([], mock_executor)
        assert results == {}

    @pytest.mark.asyncio
    async def test_execute_single_task(self) -> None:
        """Test executing single task."""
        executor = SequentialExecutor()

        async def mock_executor(
            task_name: str, output_queue: asyncio.Queue[tuple[str, str]] | None
        ) -> ExecutionResult:
            assert output_queue is None  # Sequential executor doesn't use queue
            return ExecutionResult(
                return_code=0,
                stdout=f"output from {task_name}",
                stderr="",
                command=["test"],
            )

        results = await executor.execute(["task1"], mock_executor)
        assert len(results) == 1
        assert results["task1"].success

    @pytest.mark.asyncio
    async def test_execute_multiple_tasks_in_order(self) -> None:
        """Test that tasks execute in order."""
        executor = SequentialExecutor()

        execution_order: list[str] = []

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            execution_order.append(task_name)
            await asyncio.sleep(0.01)
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["task1", "task2", "task3"], mock_executor)

        assert execution_order == ["task1", "task2", "task3"]
        assert len(results) == 3
        assert all(r.success for r in results.values())

    @pytest.mark.asyncio
    async def test_stops_on_first_failure(self) -> None:
        """Test that execution stops on first failure."""
        executor = SequentialExecutor()

        execution_order: list[str] = []

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            execution_order.append(task_name)
            if task_name == "task2":
                return ExecutionResult(return_code=1, stdout="", stderr="error", command=["test"])
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["task1", "task2", "task3"], mock_executor)

        # Should stop after task2 fails
        assert execution_order == ["task1", "task2"]
        assert len(results) == 2
        assert results["task1"].success
        assert not results["task2"].success
        assert "task3" not in results


class TestPrintFunctions:
    """Tests for output formatting functions."""

    def test_print_results_summary(self) -> None:
        """Test printing results summary table."""
        results = {
            "task1": ExecutionResult(return_code=0, stdout="", stderr="", command=["test"]),
            "task2": ExecutionResult(return_code=1, stdout="", stderr="", command=["test"]),
        }

        # Should not raise exception
        console = Console()
        print_results_summary(results, console)

    def test_print_results_summary_with_default_console(self) -> None:
        """Test printing with default console."""
        results = {
            "task1": ExecutionResult(return_code=0, stdout="", stderr="", command=["test"]),
        }

        # Should create its own console
        print_results_summary(results)

    def test_print_task_output(self) -> None:
        """Test printing task output."""
        result = ExecutionResult(
            return_code=0,
            stdout="Standard output",
            stderr="Standard error",
            command=["test"],
        )

        console = Console()
        print_task_output("task1", result, console)

    def test_print_task_output_with_empty_streams(self) -> None:
        """Test printing task output with empty stdout/stderr."""
        result = ExecutionResult(
            return_code=0,
            stdout="",
            stderr="",
            command=["test"],
        )

        console = Console()
        # Should not raise exception
        print_task_output("task1", result, console)

    def test_print_task_output_with_default_console(self) -> None:
        """Test printing with default console."""
        result = ExecutionResult(
            return_code=0,
            stdout="output",
            stderr="",
            command=["test"],
        )

        # Should create its own console
        print_task_output("task1", result)


class TestIntegrationScenarios:
    """Integration tests for complex scenarios."""

    @pytest.mark.asyncio
    async def test_mixed_success_and_failure_parallel(self) -> None:
        """Test parallel execution with mixed results."""
        executor = ParallelExecutor(on_failure=OnFailure.CONTINUE)

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            await asyncio.sleep(0.01)
            # Alternate success/failure
            success = int(task_name.replace("task", "")) % 2 == 1
            return ExecutionResult(
                return_code=0 if success else 1,
                stdout=f"output from {task_name}" if success else "",
                stderr="" if success else f"error from {task_name}",
                command=["test"],
            )

        results = await executor.execute(["task1", "task2", "task3", "task4"], mock_executor)

        assert len(results) == 4
        assert results["task1"].success
        assert not results["task2"].success
        assert results["task3"].success
        assert not results["task4"].success

    @pytest.mark.asyncio
    async def test_sequential_with_output(self) -> None:
        """Test sequential execution with output."""
        executor = SequentialExecutor()

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            return ExecutionResult(
                return_code=0,
                stdout=f"Output from {task_name}",
                stderr="",
                command=["test"],
            )

        results = await executor.execute(["task1", "task2"], mock_executor)

        assert len(results) == 2
        assert "Output from task1" in results["task1"].stdout
        assert "Output from task2" in results["task2"].stdout

    @pytest.mark.asyncio
    async def test_parallel_with_timeout_simulation(self) -> None:
        """Test parallel execution where some tasks take longer."""
        executor = ParallelExecutor()

        async def mock_executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,  # noqa: ARG001
        ) -> ExecutionResult:
            # Vary execution time
            if task_name == "slow":
                await asyncio.sleep(0.1)
            else:
                await asyncio.sleep(0.01)
            return ExecutionResult(
                return_code=0, stdout=f"output from {task_name}", stderr="", command=["test"]
            )

        results = await executor.execute(["fast1", "slow", "fast2"], mock_executor)

        assert len(results) == 3
        assert all(r.success for r in results.values())

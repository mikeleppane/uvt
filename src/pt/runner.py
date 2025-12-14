"""Task runner orchestration - the main entry point for executing tasks."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from rich.console import Console

from pt.condition_evaluator import ConditionEvaluator
from pt.config import (
    build_profile_env,
    get_profile_python,
    get_project_root,
    load_config,
    merge_env,
    resolve_path,
)
from pt.executor import ExecutionResult, UvCommand, execute_async, execute_sync
from pt.graph import build_pipeline_graph, build_task_graph
from pt.models import OnFailure, OutputMode, PtConfig, TaskConfig
from pt.parallel import (
    ParallelExecutor,
    SequentialExecutor,
    print_results_summary,
    print_task_output,
)
from pt.script_meta import merge_dependencies, parse_script_metadata


def _detect_ci_environment() -> bool:
    """Detect if running in a CI environment."""
    import os

    ci_vars = [
        "CI",
        "CONTINUOUS_INTEGRATION",  # Generic
        "GITHUB_ACTIONS",  # GitHub Actions
        "GITLAB_CI",  # GitLab CI
        "CIRCLECI",  # CircleCI
        "TRAVIS",  # Travis CI
        "JENKINS_HOME",  # Jenkins
        "BUILDKITE",  # Buildkite
    ]
    return any(os.environ.get(var) for var in ci_vars)


def _get_git_info() -> tuple[str | None, str | None]:
    """Get git branch and commit (best effort).

    Returns:
        Tuple of (branch, commit) or (None, None) if not in git repo.
    """
    try:
        import subprocess

        branch = subprocess.run(
            ["git", "rev-parse", "--abbrev-ref", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        ).stdout.strip()

        commit = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=1,
            check=False,
        ).stdout.strip()

        return (branch or None, commit or None)
    except Exception:
        return (None, None)


@dataclass
class Runner:
    """Main task runner that coordinates task execution."""

    config: PtConfig
    project_root: Path
    config_path: Path
    console: Console = field(default_factory=Console)
    verbose: bool = False
    profile: str | None = None  # Active profile name

    @classmethod
    def from_config_file(
        cls,
        config_path: Path | None = None,
        verbose: bool = False,
        profile: str | None = None,
    ) -> Runner:
        """Create a Runner from a config file.

        Args:
            config_path: Path to config file, or None to auto-discover.
            verbose: Enable verbose output.
            profile: Profile name to use (overrides PYR_PROFILE and default_profile).

        Returns:
            Configured Runner instance.
        """
        config, path = load_config(config_path)
        return cls(
            config=config,
            project_root=get_project_root(path),
            config_path=path,
            verbose=verbose,
            profile=profile,
        )

    def build_command(
        self,
        task: TaskConfig,
        task_name: str,
        extra_args: list[str] | None = None,
    ) -> UvCommand:
        """Build a UvCommand for a task.

        Args:
            task: The task configuration.
            task_name: Canonical task name.
            extra_args: Additional arguments to pass to the script/command.

        Returns:
            Configured UvCommand ready for execution.
        """
        # Resolve dependencies (including dependency group references)
        config_deps = self.config.resolve_dependencies(task)

        # Get script metadata if this is a script task
        script_deps: list[str] = []
        # Use profile Python version if set, otherwise task/project default
        python_version = task.python or get_profile_python(self.config, self.profile)

        if task.script:
            script_path = resolve_path(task.script, self.project_root)
            meta = parse_script_metadata(script_path)
            script_deps = meta.dependencies
            if meta.requires_python and not python_version:
                # Extract minimum version from requires-python
                python_version = self._extract_python_version(meta.requires_python)

        # Merge dependencies (config takes precedence)
        all_deps = merge_dependencies(script_deps, config_deps)

        # Build builtin environment variables
        builtin_env = self._build_builtin_env(task_name, task)

        # Build environment with profile support
        env = self._build_task_environment(task, builtin_env=builtin_env)

        # Build args
        args = list(task.args)
        if extra_args:
            args.extend(extra_args)

        # Resolve script path
        script: str | None = None
        if task.script:
            script = str(resolve_path(task.script, self.project_root))

        # Resolve working directory
        cwd = self.project_root
        if task.cwd:
            cwd = resolve_path(task.cwd, self.project_root)

        return UvCommand(
            script=script,
            cmd=task.cmd,
            args=args,
            dependencies=all_deps,
            python=python_version,
            env=env,
            cwd=cwd,
        )

    def _build_builtin_env(
        self,
        task_name: str,
        task: TaskConfig,
    ) -> dict[str, str]:
        """Build built-in environment variables for task execution.

        Args:
            task_name: Canonical task name
            task: Task configuration

        Returns:
            Dictionary of built-in environment variables
        """
        env: dict[str, str] = {}

        # Essential variables
        env["PT_TASK_NAME"] = task_name
        env["PT_PROJECT_ROOT"] = str(self.project_root)
        env["PT_CONFIG_FILE"] = str(self.config_path)

        # Profile
        if self.profile:
            env["PT_PROFILE"] = self.profile

        # Python version
        python_version = task.python or self.config.project.python
        if python_version:
            env["PT_PYTHON_VERSION"] = python_version

        # Tags
        if task.tags:
            env["PT_TAGS"] = ",".join(sorted(task.tags))

        # CI detection
        if _detect_ci_environment():
            env["PT_CI"] = "true"

        # Git info (best effort)
        git_branch, git_commit = _get_git_info()
        if git_branch:
            env["PT_GIT_BRANCH"] = git_branch
        if git_commit:
            env["PT_GIT_COMMIT"] = git_commit

        return env

    def _extract_python_version(self, requires_python: str) -> str | None:
        """Extract Python version from requires-python specifier."""
        import re

        # Match patterns like ">=3.10", ">=3.10,<4", "==3.11.*"
        match = re.search(r"(\d+\.\d+)", requires_python)
        return match.group(1) if match else None

    def _check_condition(self, task: TaskConfig) -> tuple[bool, str]:
        """Check if task conditions are met.

        Returns:
            Tuple of (should_run, skip_reason).
        """
        # Check declarative conditions
        if task.condition:
            evaluator = ConditionEvaluator(self.project_root)
            passed, reason = evaluator.evaluate(task.condition)
            if not passed:
                return False, reason

        # Check condition script
        if task.condition_script:
            script_path = resolve_path(task.condition_script, self.project_root)
            result = execute_sync(
                UvCommand(script=str(script_path), cwd=self.project_root),
                capture_output=True,
            )
            if not result.success:
                return False, f"Condition script '{task.condition_script}' returned non-zero"

        return True, ""

    def _build_hook_command(
        self,
        hook_script: str,
        hook_type: str,
        task_name: str,
        task: TaskConfig,
        task_exit_code: int = 0,
    ) -> UvCommand:
        """Build UvCommand for hook execution (shared by sync/async).

        Args:
            hook_script: Path to the hook script
            hook_type: Type of hook (before_task, after_success, etc.)
            task_name: Name of the task being run
            task: Task configuration
            task_exit_code: Exit code of the task (for after hooks)

        Returns:
            UvCommand configured for hook execution.
        """
        from pathlib import Path

        script_path = resolve_path(hook_script, self.project_root)

        # Build environment for hook with hook-specific variables
        hook_extra_env = {
            "PT_TASK_NAME": task_name,
            "PT_HOOK_TYPE": hook_type,
            "PT_TASK_EXIT_CODE": str(task_exit_code),
        }
        env = self._build_task_environment(task, extra_env=hook_extra_env)

        # Build command for hook execution
        return UvCommand(
            script=str(script_path),
            env=env,
            cwd=Path(task.cwd) if task.cwd else self.project_root,
            python=task.python,
        )

    def _format_hook_result(
        self, result: ExecutionResult, hook_script: str, hook_type: str
    ) -> tuple[bool, str]:
        """Format hook execution result (shared by sync/async).

        Args:
            result: Execution result from the hook
            hook_script: Path to the hook script
            hook_type: Type of hook

        Returns:
            Tuple of (success, error_message).
        """
        if result.success:
            return True, ""

        error_msg = f"Hook '{hook_script}' ({hook_type}) failed with exit code {result.return_code}"
        if result.stderr:
            error_msg += f": {result.stderr.strip()}"
        return False, error_msg

    def _build_task_environment(
        self,
        task: TaskConfig,
        extra_env: dict[str, str] | None = None,
        builtin_env: dict[str, str] | None = None,
    ) -> dict[str, str]:
        """Build complete environment for task execution.

        Merges environments in order: builtin → global/profile → task → extra
        This ensures user-defined vars can override builtin vars.

        Args:
            task: Task configuration
            extra_env: Additional environment variables to merge (highest priority)
            builtin_env: Built-in environment variables (lowest priority)

        Returns:
            Complete merged environment dictionary.
        """
        # Start with builtin env (lowest priority)
        base_env = builtin_env.copy() if builtin_env else {}

        # Merge global/profile env
        global_env = build_profile_env(self.config, self.project_root, self.profile)
        base_env.update(global_env)

        # Merge task env
        base_env.update(task.env)

        # Merge extra env (highest priority, for hooks)
        if extra_env:
            base_env.update(extra_env)

        pythonpath_lists = [task.pythonpath] if task.pythonpath else None
        return merge_env(
            {},  # No base needed since we already merged everything
            base_env,
            pythonpath_lists=pythonpath_lists,
            project_root=self.project_root,
        )

    def _execute_hook(
        self,
        hook_script: str,
        hook_type: str,
        task_name: str,
        task: TaskConfig,
        task_exit_code: int = 0,
    ) -> tuple[bool, str]:
        """Execute a task hook script.

        Args:
            hook_script: Path to the hook script
            hook_type: Type of hook (before_task, after_success, etc.)
            task_name: Name of the task being run
            task: Task configuration
            task_exit_code: Exit code of the task (for after hooks)

        Returns:
            Tuple of (success, error_message). If success is False, error_message explains why.
        """
        command = self._build_hook_command(hook_script, hook_type, task_name, task, task_exit_code)

        if self.verbose:
            self.console.print(f"[dim]Running {hook_type} hook: {hook_script}[/dim]")

        result = execute_sync(command, capture_output=not self.verbose)
        return self._format_hook_result(result, hook_script, hook_type)

    def _execute_error_handler(
        self,
        failed_task_name: str,
        error_code: int,
        stderr: str,
    ) -> None:
        """Execute global error handler if configured.

        Args:
            failed_task_name: Name of the task that failed
            error_code: Exit code of the failed task
            stderr: Error output from the failed task
        """
        error_task_name = self.config.project.on_error_task
        if not error_task_name:
            return

        # Don't run error handler for itself (avoid infinite loop)
        if error_task_name == failed_task_name:
            if self.verbose:
                self.console.print(
                    f"[yellow]Warning:[/yellow] Error handler '{error_task_name}' "
                    "failed, skipping recursive error handling"
                )
            return

        # Check if error handler task exists
        try:
            error_task = self.config.get_task(error_task_name)
        except KeyError:
            if self.verbose:
                self.console.print(
                    f"[yellow]Warning:[/yellow] Error handler task '{error_task_name}' "
                    "not found, skipping"
                )
            return

        if self.verbose:
            self.console.print(f"\n[yellow]→[/yellow] Running error handler: {error_task_name}")

        # Build error context env vars
        error_env = {
            "PT_FAILED_TASK": failed_task_name,
            "PT_ERROR_CODE": str(error_code),
            "PT_ERROR_STDERR": stderr,
        }

        # Execute error handler (ignore its result)
        try:
            command = self.build_command(error_task, error_task_name)
            # Add error context to command env
            command.env.update(error_env)

            result = execute_sync(command, capture_output=True)
            if not result.success and self.verbose:
                self.console.print(
                    f"[yellow]Warning:[/yellow] Error handler failed with "
                    f"exit code {result.return_code}"
                )
        except Exception as e:
            if self.verbose:
                self.console.print(f"[yellow]Warning:[/yellow] Error handler raised exception: {e}")

    async def _execute_error_handler_async(
        self,
        failed_task_name: str,
        error_code: int,
        stderr: str,
    ) -> None:
        """Execute global error handler asynchronously if configured.

        Args:
            failed_task_name: Name of the task that failed
            error_code: Exit code of the failed task
            stderr: Error output from the failed task
        """
        error_task_name = self.config.project.on_error_task
        if not error_task_name:
            return

        # Don't run error handler for itself (avoid infinite loop)
        if error_task_name == failed_task_name:
            if self.verbose:
                self.console.print(
                    f"[yellow]Warning:[/yellow] Error handler '{error_task_name}' "
                    "failed, skipping recursive error handling"
                )
            return

        # Check if error handler task exists
        try:
            error_task = self.config.get_task(error_task_name)
        except KeyError:
            if self.verbose:
                self.console.print(
                    f"[yellow]Warning:[/yellow] Error handler task '{error_task_name}' "
                    "not found, skipping"
                )
            return

        if self.verbose:
            self.console.print(f"\n[yellow]→[/yellow] Running error handler: {error_task_name}")

        # Build error context env vars
        error_env = {
            "PT_FAILED_TASK": failed_task_name,
            "PT_ERROR_CODE": str(error_code),
            "PT_ERROR_STDERR": stderr,
        }

        # Execute error handler (ignore its result)
        try:
            command = self.build_command(error_task, error_task_name)
            # Add error context to command env
            command.env.update(error_env)

            result = await execute_async(command, output_mode=OutputMode.BUFFERED)
            if not result.success and self.verbose:
                self.console.print(
                    f"[yellow]Warning:[/yellow] Error handler failed with "
                    f"exit code {result.return_code}"
                )
        except Exception as e:
            if self.verbose:
                self.console.print(f"[yellow]Warning:[/yellow] Error handler raised exception: {e}")

    def run_task(
        self,
        task_name: str,
        extra_args: list[str] | None = None,
    ) -> ExecutionResult:
        """Run a single task synchronously.

        Args:
            task_name: Name of the task to run.
            extra_args: Additional arguments to pass.

        Returns:
            ExecutionResult from the task.
        """
        task = self.config.get_task(task_name)

        # Check conditions
        should_run, skip_reason = self._check_condition(task)
        if not should_run:
            if self.verbose:
                self.console.print(f"[yellow]Skipping {task_name}:[/yellow] {skip_reason}")
            return ExecutionResult(
                return_code=0,
                stdout="",
                stderr="",
                command=[],
                skipped=True,
                skip_reason=skip_reason,
            )

        # Execute before_task hook
        if task.before_task:
            hook_success, hook_error = self._execute_hook(
                task.before_task, "before_task", task_name, task
            )
            if not hook_success:
                self.console.print(f"[red]Before hook failed:[/red] {hook_error}")
                return ExecutionResult(
                    return_code=1,
                    stdout="",
                    stderr=hook_error,
                    command=[],
                    skipped=True,
                    skip_reason=f"Before hook failed: {hook_error}",
                )

        # If task only has depends_on, run dependencies
        if task.script is None and task.cmd is None:
            return self._run_task_dependencies(task_name, extra_args)

        command = self.build_command(task, task_name, extra_args)

        if self.verbose:
            self.console.print(f"[dim]Running: {' '.join(command.build())}[/dim]")

        result = execute_sync(command, capture_output=not self.verbose, timeout=task.timeout)

        if self.verbose or not result.success:
            print_task_output(task_name, result, self.console)

        # Execute after hooks based on result
        if result.success and task.after_success:
            self._execute_hook(
                task.after_success, "after_success", task_name, task, result.return_code
            )
        elif not result.success and task.after_failure:
            self._execute_hook(
                task.after_failure, "after_failure", task_name, task, result.return_code
            )

        # Execute after_task hook (always runs)
        if task.after_task:
            self._execute_hook(task.after_task, "after_task", task_name, task, result.return_code)

        # Execute error handler if task failed and ignore_errors is not set
        if not result.success and not task.ignore_errors:
            self._execute_error_handler(task_name, result.return_code, result.stderr)

        # Handle ignore_errors
        if not result.success and task.ignore_errors:
            if self.verbose:
                self.console.print(
                    f"[yellow]Task {task_name} failed but ignore_errors=true[/yellow]"
                )
            return ExecutionResult(
                return_code=0,  # Treat as success
                stdout=result.stdout,
                stderr=result.stderr,
                command=result.command,
                timed_out=result.timed_out,
            )

        return result

    def _run_task_dependencies(
        self,
        task_name: str,
        extra_args: list[str] | None = None,
    ) -> ExecutionResult:
        """Run a task that only has dependencies (no script/cmd)."""
        task = self.config.get_task(task_name)

        if task.parallel:
            return asyncio.run(self._run_parallel_dependencies(task_name, extra_args))
        else:
            return self._run_sequential_dependencies(task_name, extra_args)

    def _run_sequential_dependencies(
        self,
        task_name: str,
        extra_args: list[str] | None = None,
    ) -> ExecutionResult:
        """Run task dependencies sequentially."""
        graph = build_task_graph(self.config, [task_name])
        execution_order = graph.topological_sort()

        # Remove the parent task itself (it has no script/cmd)
        if task_name in execution_order:
            execution_order.remove(task_name)

        for dep_name in execution_order:
            dep_task = self.config.get_task(dep_name)
            if dep_task.script is None and dep_task.cmd is None:
                continue

            result = self.run_task(dep_name, extra_args)
            if not result.success:
                return result

        return ExecutionResult(
            return_code=0,
            stdout="",
            stderr="",
            command=[],
        )

    async def _run_parallel_dependencies(
        self,
        task_name: str,
        extra_args: list[str] | None = None,
    ) -> ExecutionResult:
        """Run task dependencies in parallel."""
        task = self.config.get_task(task_name)
        dep_names = [dep if isinstance(dep, str) else dep.task for dep in task.depends_on]

        async def executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,
        ) -> ExecutionResult:
            dep_task = self.config.get_task(task_name)
            command = self.build_command(dep_task, task_name, extra_args)
            return await execute_async(
                command,
                output_mode=OutputMode.BUFFERED,
                on_stdout=output_queue,
                task_name=task_name,
            )

        parallel = ParallelExecutor(
            on_failure=OnFailure.FAIL_FAST,
            output_mode=OutputMode.BUFFERED,
            console=self.console,
        )

        results = await parallel.execute(dep_names, executor)

        # Check for failures
        failed = [name for name, result in results.items() if not result.success]
        if failed:
            return ExecutionResult(
                return_code=1,
                stdout="",
                stderr=f"Tasks failed: {', '.join(failed)}",
                command=[],
            )

        return ExecutionResult(
            return_code=0,
            stdout="",
            stderr="",
            command=[],
        )

    async def _execute_hook_async(
        self,
        hook_script: str,
        hook_type: str,
        task_name: str,
        task: TaskConfig,
        task_exit_code: int = 0,
    ) -> tuple[bool, str]:
        """Execute a task hook script asynchronously.

        Args:
            hook_script: Path to the hook script
            hook_type: Type of hook (before_task, after_success, etc.)
            task_name: Name of the task being run
            task: Task configuration
            task_exit_code: Exit code of the task (for after hooks)

        Returns:
            Tuple of (success, error_message). If success is False, error_message explains why.
        """
        command = self._build_hook_command(hook_script, hook_type, task_name, task, task_exit_code)

        if self.verbose:
            self.console.print(f"[dim]Running {hook_type} hook: {hook_script}[/dim]")

        result = await execute_async(command, output_mode=OutputMode.BUFFERED)
        return self._format_hook_result(result, hook_script, hook_type)

    async def run_tasks_async(
        self,
        task_names: list[str],
        parallel: bool = False,
        on_failure: OnFailure = OnFailure.FAIL_FAST,
        output_mode: OutputMode = OutputMode.BUFFERED,
    ) -> dict[str, ExecutionResult]:
        """Run multiple tasks asynchronously.

        Args:
            task_names: Names of tasks to run.
            parallel: Run tasks in parallel (otherwise sequential).
            on_failure: Behavior when a task fails.
            output_mode: How to display output.

        Returns:
            Dict mapping task names to results.
        """

        async def executor(
            task_name: str,
            output_queue: asyncio.Queue[tuple[str, str]] | None,
        ) -> ExecutionResult:
            task = self.config.get_task(task_name)

            # Check conditions
            should_run, skip_reason = self._check_condition(task)
            if not should_run:
                if self.verbose:
                    self.console.print(f"[yellow]Skipping {task_name}:[/yellow] {skip_reason}")
                return ExecutionResult(
                    return_code=0,
                    stdout="",
                    stderr="",
                    command=[],
                    skipped=True,
                    skip_reason=skip_reason,
                )

            # Execute before_task hook
            if task.before_task:
                hook_success, hook_error = await self._execute_hook_async(
                    task.before_task, "before_task", task_name, task
                )
                if not hook_success:
                    self.console.print(f"[red]Before hook failed:[/red] {hook_error}")
                    return ExecutionResult(
                        return_code=1,
                        stdout="",
                        stderr=hook_error,
                        command=[],
                        skipped=True,
                        skip_reason=f"Before hook failed: {hook_error}",
                    )

            # Execute task
            command = self.build_command(task, task_name)
            result = await execute_async(
                command,
                output_mode=output_mode,
                on_stdout=output_queue,
                task_name=task_name,
                timeout=task.timeout,
            )

            # Execute after hooks based on result
            if result.success and task.after_success:
                await self._execute_hook_async(
                    task.after_success, "after_success", task_name, task, result.return_code
                )
            elif not result.success and task.after_failure:
                await self._execute_hook_async(
                    task.after_failure, "after_failure", task_name, task, result.return_code
                )

            # Execute after_task hook (always runs)
            if task.after_task:
                await self._execute_hook_async(
                    task.after_task, "after_task", task_name, task, result.return_code
                )

            # Execute error handler if task failed and ignore_errors is not set
            if not result.success and not task.ignore_errors:
                await self._execute_error_handler_async(task_name, result.return_code, result.stderr)

            # Handle ignore_errors
            if not result.success and task.ignore_errors:
                if self.verbose:
                    self.console.print(
                        f"[yellow]Task {task_name} failed but ignore_errors=true[/yellow]"
                    )
                return ExecutionResult(
                    return_code=0,  # Treat as success
                    stdout=result.stdout,
                    stderr=result.stderr,
                    command=result.command,
                    timed_out=result.timed_out,
                )

            return result

        if parallel:
            runner: ParallelExecutor | SequentialExecutor = ParallelExecutor(
                on_failure=on_failure,
                output_mode=output_mode,
                console=self.console,
            )
        else:
            runner = SequentialExecutor(console=self.console)

        return await runner.execute(task_names, executor)

    def run_tasks(
        self,
        task_names: list[str],
        parallel: bool = False,
        on_failure: OnFailure = OnFailure.FAIL_FAST,
        output_mode: OutputMode = OutputMode.BUFFERED,
    ) -> dict[str, ExecutionResult]:
        """Run multiple tasks synchronously (wrapper around async version)."""
        return asyncio.run(self.run_tasks_async(task_names, parallel, on_failure, output_mode))

    def run_pipeline(
        self,
        pipeline_name: str,
    ) -> dict[str, ExecutionResult]:
        """Run a pipeline.

        Args:
            pipeline_name: Name of the pipeline to run.

        Returns:
            Dict mapping task names to results.
        """
        pipeline = self.config.get_pipeline(pipeline_name)
        stages = build_pipeline_graph(self.config, pipeline_name)

        all_results: dict[str, ExecutionResult] = {}

        for stage_tasks, parallel in stages:
            self.console.print(f"\n[bold]Stage:[/bold] {', '.join(stage_tasks)}")

            results = self.run_tasks(
                stage_tasks,
                parallel=parallel,
                on_failure=pipeline.on_failure,
                output_mode=pipeline.output,
            )
            all_results.update(results)

            # Check for failures
            failed = [name for name, result in results.items() if not result.success]
            if failed and pipeline.on_failure != OnFailure.CONTINUE:
                self.console.print(f"[red]Stage failed:[/red] {', '.join(failed)}")
                break

        print_results_summary(all_results, self.console)
        return all_results

    def run_script(
        self,
        script_path: str,
        args: list[str] | None = None,
    ) -> ExecutionResult:
        """Run a standalone script with pyr context.

        Uses global env and dependencies from config, plus script's inline metadata.

        Args:
            script_path: Path to the Python script.
            args: Arguments to pass to the script.

        Returns:
            ExecutionResult from the script.
        """
        resolved_path = resolve_path(script_path, self.project_root)

        # Parse script metadata
        meta = parse_script_metadata(resolved_path)

        # Get common dependencies from config
        common_deps = self.config.dependencies.get("common", [])
        all_deps = merge_dependencies(meta.dependencies, common_deps)

        # Build environment from config with profile support
        env = build_profile_env(self.config, self.project_root, self.profile)

        # Determine Python version (profile can override)
        python_version = get_profile_python(self.config, self.profile)
        if meta.requires_python:
            python_version = self._extract_python_version(meta.requires_python) or python_version

        command = UvCommand(
            script=str(resolved_path),
            args=args or [],
            dependencies=all_deps,
            python=python_version,
            env=env,
            cwd=self.project_root,
        )

        if self.verbose:
            self.console.print(f"[dim]Running: {' '.join(command.build())}[/dim]")

        result = execute_sync(command, capture_output=not self.verbose)

        if not result.success:
            print_task_output(script_path, result, self.console)

        return result

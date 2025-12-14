"""UV command builder and subprocess executor."""

from __future__ import annotations

import asyncio
import contextlib
import os
import shlex
import subprocess
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, TextIO

if TYPE_CHECKING:
    from pathlib import Path

from uvr.models import OutputMode


@dataclass
class ExecutionResult:
    """Result of executing a command."""

    return_code: int
    stdout: str
    stderr: str
    command: list[str]
    timed_out: bool = False
    skipped: bool = False
    skip_reason: str = ""

    @property
    def success(self) -> bool:
        """Whether the command succeeded (return code 0 or skipped)."""
        return self.return_code == 0 or self.skipped


@dataclass
class UvCommand:
    """Builder for uv run commands."""

    script: str | None = None
    cmd: str | None = None
    args: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    python: str | None = None
    env: dict[str, str] = field(default_factory=dict)
    cwd: Path | None = None
    runner: str | None = None  # Runner prefix to prepend
    stdout_redirect: str | None = None  # stdout redirection
    stderr_redirect: str | None = None  # stderr redirection

    def build(self) -> list[str]:
        """Build the complete uv command as a list of arguments."""
        command = ["uv", "run"]

        # Add Python version if specified
        if self.python:
            command.extend(["--python", self.python])

        # Add dependencies
        for dep in self.dependencies:
            command.extend(["--with", dep])

        # Add runner prefix if specified
        runner_parts = []
        if self.runner:
            runner_parts = shlex.split(self.runner)

        # Add script or command
        if self.script:
            # For scripts: uv run [--python X] [--with Y] runner script args
            if runner_parts:
                command.extend(runner_parts)
            command.append(self.script)
        elif self.cmd:
            # For cmd mode: uv run [--python X] [--with Y] runner cmd
            if runner_parts:
                command.extend(runner_parts)
            command.extend(shlex.split(self.cmd))

        # Add additional arguments
        command.extend(self.args)

        return command

    def build_env(self) -> dict[str, str]:
        """Build environment dict, merging with current environment."""
        result = os.environ.copy()
        result.update(self.env)
        return result


def _prepare_output_redirect(
    redirect_value: str | None,
    cwd: Path | None,
) -> int | TextIO | None:
    """Prepare output redirection for subprocess.

    Args:
        redirect_value: "null", "inherit", or file path
        cwd: Working directory (for resolving relative paths)

    Returns:
        File descriptor, subprocess constant, or None
    """
    from pathlib import Path

    if redirect_value is None:
        return None

    if redirect_value == "null":
        return subprocess.DEVNULL

    if redirect_value == "inherit":
        return None  # subprocess default

    # It's a file path
    file_path = Path(redirect_value)
    if not file_path.is_absolute() and cwd:
        file_path = cwd / file_path

    # Ensure parent directory exists
    file_path.parent.mkdir(parents=True, exist_ok=True)

    # Open in append mode
    return file_path.open("a")  # Caller must close this


def execute_sync(
    command: UvCommand,
    capture_output: bool = True,
    timeout: int | None = None,
) -> ExecutionResult:
    """Execute a uv command synchronously.

    Args:
        command: The UvCommand to execute.
        capture_output: Whether to capture stdout/stderr.
        timeout: Timeout in seconds, or None for no timeout.

    Returns:
        ExecutionResult with return code and output.
    """
    cmd_list = command.build()
    env = command.build_env()

    # Handle output redirection
    stdout_fd: int | TextIO | None = None
    stderr_fd: int | TextIO | None = None
    files_to_close: list[TextIO] = []

    try:
        # Determine stdout handling
        if command.stdout_redirect:
            stdout_result = _prepare_output_redirect(command.stdout_redirect, command.cwd)
            if stdout_result == subprocess.DEVNULL:
                stdout_fd = subprocess.DEVNULL
            elif stdout_result is None:
                stdout_fd = None  # Inherit
            else:
                # It's a TextIO file handle
                stdout_fd = stdout_result
                files_to_close.append(stdout_result)  # type: ignore[arg-type]
        elif capture_output:
            stdout_fd = subprocess.PIPE
        else:
            stdout_fd = None

        # Determine stderr handling
        if command.stderr_redirect:
            stderr_result = _prepare_output_redirect(command.stderr_redirect, command.cwd)
            if stderr_result == subprocess.DEVNULL:
                stderr_fd = subprocess.DEVNULL
            elif stderr_result is None:
                stderr_fd = None  # Inherit
            else:
                # It's a TextIO file handle
                stderr_fd = stderr_result
                files_to_close.append(stderr_result)  # type: ignore[arg-type]
        elif capture_output:
            stderr_fd = subprocess.PIPE
        else:
            stderr_fd = None

        result = subprocess.run(
            cmd_list,
            env=env,
            cwd=command.cwd,
            stdout=stdout_fd,
            stderr=stderr_fd,
            text=True,
            check=False,
            timeout=timeout,
        )
        return ExecutionResult(
            return_code=result.returncode,
            stdout=result.stdout if capture_output and not command.stdout_redirect else "",
            stderr=result.stderr if capture_output and not command.stderr_redirect else "",
            command=cmd_list,
        )
    except subprocess.TimeoutExpired:
        return ExecutionResult(
            return_code=124,
            stdout="",
            stderr=f"Command timed out after {timeout} seconds",
            command=cmd_list,
            timed_out=True,
        )
    except FileNotFoundError as e:
        return ExecutionResult(
            return_code=127,
            stdout="",
            stderr=f"Command not found: {e.filename}. Is uv installed?",
            command=cmd_list,
        )
    except OSError as e:
        return ExecutionResult(
            return_code=1,
            stdout="",
            stderr=f"Failed to execute command: {e}",
            command=cmd_list,
        )
    finally:
        # Close any file descriptors we opened
        for fd in files_to_close:
            with contextlib.suppress(Exception):
                fd.close()


async def execute_async(
    command: UvCommand,
    output_mode: OutputMode = OutputMode.BUFFERED,
    on_stdout: asyncio.Queue[tuple[str, str]] | None = None,
    task_name: str = "",
    timeout: int | None = None,
) -> ExecutionResult:
    """Execute a uv command asynchronously.

    Args:
        command: The UvCommand to execute.
        output_mode: How to handle output (buffered or interleaved).
        on_stdout: Queue to send output lines for interleaved mode.
        task_name: Name of the task for labeling output.
        timeout: Timeout in seconds, or None for no timeout.

    Returns:
        ExecutionResult with return code and output.
    """
    cmd_list = command.build()
    env = command.build_env()

    try:
        process = await asyncio.create_subprocess_exec(
            *cmd_list,
            env=env,
            cwd=command.cwd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except FileNotFoundError:
        return ExecutionResult(
            return_code=127,
            stdout="",
            stderr="Command not found: uv. Is uv installed?",
            command=cmd_list,
        )
    except OSError as e:
        return ExecutionResult(
            return_code=1,
            stdout="",
            stderr=f"Failed to execute command: {e}",
            command=cmd_list,
        )

    stdout_lines: list[str] = []
    stderr_lines: list[str] = []

    async def read_stream(
        stream: asyncio.StreamReader,
        lines: list[str],
        _is_stderr: bool = False,
    ) -> None:
        while True:
            line = await stream.readline()
            if not line:
                break
            decoded = line.decode("utf-8", errors="replace")
            lines.append(decoded)
            if output_mode == OutputMode.INTERLEAVED and on_stdout:
                prefix = f"[{task_name}] " if task_name else ""
                await on_stdout.put((task_name, prefix + decoded))

    if process.stdout is None or process.stderr is None:
        raise RuntimeError("Failed to create subprocess with stdout/stderr pipes")

    try:
        await asyncio.wait_for(
            asyncio.gather(
                read_stream(process.stdout, stdout_lines),
                read_stream(process.stderr, stderr_lines, _is_stderr=True),
            ),
            timeout=timeout,
        )
        return_code = await process.wait()
    except asyncio.TimeoutError:
        process.kill()
        # Give stream readers a chance to finish reading buffered data
        with contextlib.suppress(asyncio.TimeoutError):
            await asyncio.wait_for(
                asyncio.gather(
                    read_stream(process.stdout, stdout_lines),
                    read_stream(process.stderr, stderr_lines, _is_stderr=True),
                ),
                timeout=1.0,
            )
        await process.wait()
        return ExecutionResult(
            return_code=124,
            stdout="".join(stdout_lines),
            stderr=f"Command timed out after {timeout} seconds",
            command=cmd_list,
            timed_out=True,
        )

    return ExecutionResult(
        return_code=return_code,
        stdout="".join(stdout_lines),
        stderr="".join(stderr_lines),
        command=cmd_list,
    )


def check_uv_installed() -> bool:
    """Check if uv is installed and accessible."""
    try:
        result = subprocess.run(
            ["uv", "--version"],
            capture_output=True,
            text=True,
            check=False,
        )
        return result.returncode == 0
    except FileNotFoundError:
        return False

"""Tests for global error handler feature."""

import textwrap
from pathlib import Path

from uvtx.config import load_config
from uvtx.runner import Runner


def test_error_handler_runs_on_failure(tmp_path: Path) -> None:
    """Test that error handler runs when task fails."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "error.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "cleanup"

            [tasks.failing]
            cmd = "bash"
            args = ["-c", "exit 1"]

            [tasks.cleanup]
            cmd = "bash"
            args = ["-c", "echo 'Error handler ran' > {log_file}"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("failing")

    # Task should fail
    assert not result.success
    assert result.return_code == 1

    # Error handler should have run
    assert log_file.exists()
    assert "Error handler ran" in log_file.read_text()


def test_error_handler_not_run_on_success(tmp_path: Path) -> None:
    """Test that error handler doesn't run for successful tasks."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "error.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "cleanup"

            [tasks.passing]
            cmd = "bash"
            args = ["-c", "exit 0"]

            [tasks.cleanup]
            cmd = "bash"
            args = ["-c", "echo 'Should not run' > {log_file}"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("passing")

    # Task should succeed
    assert result.success

    # Error handler should NOT have run
    assert not log_file.exists()


def test_error_handler_skipped_for_ignore_errors(tmp_path: Path) -> None:
    """Test that error handler doesn't run for ignore_errors tasks."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "error.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "cleanup"

            [tasks.optional]
            cmd = "bash"
            args = ["-c", "exit 1"]
            ignore_errors = true

            [tasks.cleanup]
            cmd = "bash"
            args = ["-c", "echo 'Should not run' > {log_file}"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("optional")

    # Task should be treated as success due to ignore_errors
    assert result.success

    # Error handler should NOT have run
    assert not log_file.exists()


def test_error_handler_receives_context_vars(tmp_path: Path) -> None:
    """Test that error handler receives UVR_FAILED_TASK, UVR_ERROR_CODE, UVR_ERROR_STDERR."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "context.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "log_error"

            [tasks.failing]
            cmd = "bash"
            args = ["-c", "echo 'Task failed' >&2 && exit 42"]

            [tasks.log_error]
            cmd = "bash"
            args = ["-c", "env | grep '^UVR_' > {log_file}"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("failing")

    # Task should fail
    assert not result.success

    # Check that error handler received context vars
    assert log_file.exists()
    content = log_file.read_text()
    assert "UVR_FAILED_TASK=failing" in content
    assert "UVR_ERROR_CODE=42" in content
    assert "UVR_ERROR_STDERR" in content


def test_error_handler_not_configured(tmp_path: Path) -> None:
    """Test that no error handler runs when not configured."""
    config_file = tmp_path / "uvt.toml"

    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.failing]
            cmd = "bash"
            args = ["-c", "exit 1"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("failing")

    # Task should fail normally
    assert not result.success
    # No error - just runs without error handler


def test_error_handler_task_not_found(tmp_path: Path) -> None:
    """Test that missing error handler is handled gracefully."""
    config_file = tmp_path / "uvt.toml"

    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"
            on_error_task = "nonexistent"

            [tasks.failing]
            cmd = "bash"
            args = ["-c", "exit 1"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("failing")

    # Task should still fail, but shouldn't crash
    assert not result.success


def test_error_handler_itself_fails(tmp_path: Path) -> None:
    """Test that error handler failure doesn't crash."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "attempted.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "bad_cleanup"

            [tasks.failing]
            cmd = "bash"
            args = ["-c", "exit 1"]

            [tasks.bad_cleanup]
            cmd = "bash"
            args = ["-c", "echo 'Attempted' > {log_file} && exit 1"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("failing")

    # Original task should still fail
    assert not result.success

    # Error handler was attempted
    assert log_file.exists()


def test_error_handler_recursive_prevention(tmp_path: Path) -> None:
    """Test that error handler doesn't run for itself (infinite loop prevention)."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "recursive.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "self_healing"

            [tasks.self_healing]
            cmd = "bash"
            args = ["-c", "echo 'Ran once' >> {log_file} && exit 1"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)
    result = runner.run_task("self_healing")

    # Task should fail
    assert not result.success

    # Should only run once (not recursively)
    if log_file.exists():
        assert log_file.read_text().count("Ran once") == 1


def test_error_handler_with_multiple_failures(tmp_path: Path) -> None:
    """Test error handler with multiple task failures."""
    config_file = tmp_path / "uvt.toml"
    log_file = tmp_path / "errors.log"

    config_file.write_text(
        textwrap.dedent(f"""
            [project]
            name = "test"
            on_error_task = "log_error"

            [tasks.fail1]
            cmd = "bash"
            args = ["-c", "exit 1"]

            [tasks.fail2]
            cmd = "bash"
            args = ["-c", "exit 2"]

            [tasks.log_error]
            cmd = "bash"
            args = ["-c", "echo \\\"$UVR_FAILED_TASK:$UVR_ERROR_CODE\\\" >> {log_file}"]
        """)
    )

    runner = Runner.from_config_file(config_file, verbose=False)

    result1 = runner.run_task("fail1")
    result2 = runner.run_task("fail2")

    # Both should fail
    assert not result1.success
    assert not result2.success

    # Error handler should have run for both
    assert log_file.exists()
    content = log_file.read_text()
    assert "fail1:1" in content
    assert "fail2:2" in content


def test_error_handler_optional_field(tmp_path: Path) -> None:
    """Test that on_error_task is optional."""
    config_file = tmp_path / "uvt.toml"

    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
        """)
    )

    config, _ = load_config(config_file)
    assert config.project.on_error_task is None

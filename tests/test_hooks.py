"""Tests for task hooks."""

from pathlib import Path
from textwrap import dedent

from uvtx.runner import Runner


class TestTaskHooks:
    """Tests for task hook execution."""

    def test_before_task_hook_success(self, tmp_path: Path) -> None:
        """Test that before_task hook runs before the task."""
        # Create hook script that writes to a file
        hook_script = tmp_path / "before_hook.py"
        hook_script.write_text(
            dedent("""\
            from pathlib import Path
            Path("before_hook_ran.txt").write_text("before")
            """)
        )

        # Create main task script
        task_script = tmp_path / "task.py"
        task_script.write_text(
            dedent("""\
            from pathlib import Path
            # Check that before hook ran
            assert Path("before_hook_ran.txt").exists()
            Path("task_ran.txt").write_text("task")
            """)
        )

        # Create config
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            script = "task.py"
            before_task = "before_hook.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        assert result.success
        assert (tmp_path / "before_hook_ran.txt").exists()
        assert (tmp_path / "task_ran.txt").exists()

    def test_before_task_hook_failure_stops_task(self, tmp_path: Path) -> None:
        """Test that failing before_task hook prevents task execution."""
        # Create failing hook script
        hook_script = tmp_path / "before_hook.py"
        hook_script.write_text("import sys; sys.exit(1)")

        # Create task script that should not run
        task_script = tmp_path / "task.py"
        task_script.write_text('from pathlib import Path; Path("task_ran.txt").write_text("task")')

        # Create config
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            script = "task.py"
            before_task = "before_hook.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        # When a before hook fails, the result is skipped but return_code is 1
        assert result.return_code == 1
        assert result.skipped
        assert "Before hook failed" in result.skip_reason
        # Task should not have run
        assert not (tmp_path / "task_ran.txt").exists()

    def test_after_success_hook(self, tmp_path: Path) -> None:
        """Test that after_success hook runs only when task succeeds."""
        # Create success hook
        success_hook = tmp_path / "after_success.py"
        success_hook.write_text(
            'from pathlib import Path; Path("success_hook_ran.txt").write_text("success")'
        )

        # Create failure hook
        failure_hook = tmp_path / "after_failure.py"
        failure_hook.write_text(
            'from pathlib import Path; Path("failure_hook_ran.txt").write_text("failure")'
        )

        # Create successful task
        task_script = tmp_path / "task.py"
        task_script.write_text("print('success')")

        # Create config
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            script = "task.py"
            after_success = "after_success.py"
            after_failure = "after_failure.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        assert result.success
        assert (tmp_path / "success_hook_ran.txt").exists()
        assert not (tmp_path / "failure_hook_ran.txt").exists()

    def test_after_failure_hook(self, tmp_path: Path) -> None:
        """Test that after_failure hook runs only when task fails."""
        # Create success hook
        success_hook = tmp_path / "after_success.py"
        success_hook.write_text(
            'from pathlib import Path; Path("success_hook_ran.txt").write_text("success")'
        )

        # Create failure hook
        failure_hook = tmp_path / "after_failure.py"
        failure_hook.write_text(
            'from pathlib import Path; Path("failure_hook_ran.txt").write_text("failure")'
        )

        # Create failing task
        task_script = tmp_path / "task.py"
        task_script.write_text("import sys; sys.exit(1)")

        # Create config
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            script = "task.py"
            after_success = "after_success.py"
            after_failure = "after_failure.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        assert not result.success
        assert not (tmp_path / "success_hook_ran.txt").exists()
        assert (tmp_path / "failure_hook_ran.txt").exists()

    def test_after_task_hook_always_runs(self, tmp_path: Path) -> None:
        """Test that after_task hook runs regardless of task result."""
        # Create after_task hook
        after_hook = tmp_path / "after_task.py"
        after_hook.write_text(
            'from pathlib import Path; Path("after_task_ran.txt").write_text("cleanup")'
        )

        # Test with successful task
        task_script = tmp_path / "task.py"
        task_script.write_text("print('success')")

        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            script = "task.py"
            after_task = "after_task.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        assert result.success
        assert (tmp_path / "after_task_ran.txt").exists()

        # Clean up and test with failing task
        (tmp_path / "after_task_ran.txt").unlink()
        task_script.write_text("import sys; sys.exit(1)")

        result = runner.run_task("test")

        assert not result.success
        assert (tmp_path / "after_task_ran.txt").exists()

    def test_hook_environment_variables(self, tmp_path: Path) -> None:
        """Test that hooks receive UVR_ environment variables."""
        # Create hook that checks environment variables
        hook_script = tmp_path / "check_env.py"
        hook_script.write_text(
            dedent("""\
            import os
            from pathlib import Path

            task_name = os.environ.get("UVR_TASK_NAME")
            hook_type = os.environ.get("UVR_HOOK_TYPE")
            exit_code = os.environ.get("UVR_TASK_EXIT_CODE")

            Path("hook_env.txt").write_text(f"{task_name},{hook_type},{exit_code}")
            """)
        )

        # Create task
        task_script = tmp_path / "task.py"
        task_script.write_text("print('task')")

        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.mytask]
            script = "task.py"
            after_success = "check_env.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("mytask")

        assert result.success
        env_data = (tmp_path / "hook_env.txt").read_text()
        assert "mytask" in env_data
        assert "after_success" in env_data
        assert "0" in env_data  # Success exit code

    def test_hook_inherits_task_environment(self, tmp_path: Path) -> None:
        """Test that hooks inherit task environment variables."""
        # Create hook that checks custom env var
        hook_script = tmp_path / "check_env.py"
        hook_script.write_text(
            dedent("""\
            import os
            from pathlib import Path

            custom_var = os.environ.get("CUSTOM_VAR", "not_set")
            Path("custom_var.txt").write_text(custom_var)
            """)
        )

        # Create task
        task_script = tmp_path / "task.py"
        task_script.write_text("print('task')")

        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            script = "task.py"
            before_task = "check_env.py"
            env = { CUSTOM_VAR = "test_value" }
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("test")

        assert result.success
        assert (tmp_path / "custom_var.txt").read_text() == "test_value"

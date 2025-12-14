"""Tests for pt.runner - Task execution orchestration."""

from pathlib import Path
from textwrap import dedent

import pytest

from pt.config import load_config
from pt.runner import Runner


class TestRunnerCreation:
    """Tests for Runner initialization."""

    def test_from_config_file_basic(self, tmp_path: Path) -> None:
        """Test creating Runner from config file."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo test"
            """)
        )

        runner = Runner.from_config_file(config_file)
        assert runner.config.project.name == "test"
        assert runner.project_root == tmp_path
        assert not runner.verbose

    def test_from_config_file_with_verbose(self, tmp_path: Path) -> None:
        """Test creating Runner with verbose mode."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo test"
            """)
        )

        runner = Runner.from_config_file(config_file, verbose=True)
        assert runner.verbose is True

    def test_from_config_file_with_profile(self, tmp_path: Path) -> None:
        """Test creating Runner with profile."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [profiles.dev]
                env = {DEBUG = "1"}

                [tasks.test]
                cmd = "echo test"
            """)
        )

        runner = Runner.from_config_file(config_file, profile="dev")
        assert runner.profile == "dev"


class TestRunTask:
    """Tests for run_task method."""

    def test_run_simple_cmd(self, tmp_path: Path) -> None:
        """Test running a simple command task."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.hello]
                cmd = "echo hello"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("hello")

        assert result.success
        assert result.return_code == 0
        assert "hello" in result.stdout

    def test_run_script_task(self, tmp_path: Path) -> None:
        """Test running a Python script task."""
        script = tmp_path / "script.py"
        script.write_text('print("from script")')

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.script]
                script = "script.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("script")

        assert result.success
        assert "from script" in result.stdout

    def test_run_task_with_args(self, tmp_path: Path) -> None:
        """Test running task with arguments."""
        script = tmp_path / "script.py"
        script.write_text(
            dedent("""\
                import sys
                print(" ".join(sys.argv[1:]))
            """)
        )

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.script]
                script = "script.py"
                args = ["arg1", "arg2"]
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("script")

        assert result.success
        assert "arg1 arg2" in result.stdout

    def test_run_task_with_cwd(self, tmp_path: Path) -> None:
        """Test running task with custom working directory."""
        subdir = tmp_path / "subdir"
        subdir.mkdir()

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.pwd]
                cmd = "pwd"
                cwd = "subdir"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("pwd")

        assert result.success
        assert "subdir" in result.stdout

    def test_run_task_with_env(self, tmp_path: Path) -> None:
        """Test running task with environment variables."""
        script = tmp_path / "print_env.py"
        script.write_text(
            dedent("""\
                import os
                print(os.environ.get("TEST_VAR", "not_set"))
            """)
        )

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.env]
                script = "print_env.py"
                env = {TEST_VAR = "test_value"}
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("env")

        assert result.success
        assert "test_value" in result.stdout

    def test_run_task_not_found(self, tmp_path: Path) -> None:
        """Test running non-existent task raises KeyError with suggestion."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo test"
            """)
        )

        runner = Runner.from_config_file(config_file)
        with pytest.raises(KeyError, match="Did you mean"):
            runner.run_task("tets")  # Typo should trigger suggestion

    def test_run_task_with_ignore_errors(self, tmp_path: Path) -> None:
        """Test running task that fails but has ignore_errors=true."""
        script = tmp_path / "fail.py"
        script.write_text("import sys; sys.exit(1)")

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.fail]
                script = "fail.py"
                ignore_errors = true
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("fail")

        # Task failed but ignore_errors converts it to success
        assert result.success
        assert result.return_code == 0


class TestRunTaskWithDependencies:
    """Tests for task dependency execution."""

    def test_run_task_with_single_dependency(self, tmp_path: Path) -> None:
        """Test running task with one dependency (meta-task)."""
        output_file = tmp_path / "output.txt"

        setup_script = tmp_path / "setup.py"
        setup_script.write_text(f'open("{output_file}", "w").write("setup\\n")')

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.setup]
                script = "setup.py"

                [tasks.main]
                depends_on = ["setup"]
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("main")

        assert result.success
        # Dependency should have run
        assert output_file.exists()
        assert "setup" in output_file.read_text()

    def test_run_task_with_multiple_dependencies(self, tmp_path: Path) -> None:
        """Test running task with multiple dependencies."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.dep1]
                cmd = "echo dep1"

                [tasks.dep2]
                cmd = "echo dep2"

                [tasks.main]
                cmd = "echo main"
                depends_on = ["dep1", "dep2"]
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("main")

        assert result.success

    def test_dependency_failure_stops_execution(self, tmp_path: Path) -> None:
        """Test that dependency failure prevents main task from succeeding."""
        fail_script = tmp_path / "fail.py"
        fail_script.write_text("import sys; sys.exit(1)")

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.failing_dep]
                script = "fail.py"

                [tasks.main]
                depends_on = ["failing_dep"]
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("main")

        # Main task should fail because dependency failed
        assert not result.success


class TestRunTaskWithConditions:
    """Tests for conditional task execution."""

    def test_run_task_with_platform_condition_pass(self, tmp_path: Path) -> None:
        """Test task with matching platform condition."""
        import platform

        current_platform = platform.system().lower()

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent(f"""\
                [project]
                name = "test"

                [tasks.platform_task]
                cmd = "echo platform"
                condition.platforms = ["{current_platform}"]
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("platform_task")

        assert result.success
        assert "platform" in result.stdout

    def test_run_task_with_platform_condition_skip(self, tmp_path: Path) -> None:
        """Test task with non-matching platform condition is skipped."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.platform_task]
                cmd = "echo platform"
                condition.platforms = ["nonexistent"]
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("platform_task")

        assert result.skipped
        assert "platform" in result.skip_reason.lower()

    def test_run_task_with_env_condition(self, tmp_path: Path) -> None:
        """Test task with environment variable condition."""
        import os

        os.environ["TEST_CONDITION"] = "1"

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.env_task]
                cmd = "echo env"
                condition.env_set = ["TEST_CONDITION"]
            """)
        )

        try:
            runner = Runner.from_config_file(config_file)
            result = runner.run_task("env_task")

            assert result.success
        finally:
            del os.environ["TEST_CONDITION"]


class TestRunTaskWithProfile:
    """Tests for task execution with profiles."""

    def test_run_task_with_profile_env(self, tmp_path: Path) -> None:
        """Test running task with profile environment."""
        script = tmp_path / "check_env.py"
        script.write_text(
            dedent("""\
                import os
                print(os.environ.get("MODE", "not_set"))
            """)
        )

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [profiles.dev]
                env = {MODE = "development"}

                [tasks.check_env]
                script = "check_env.py"
            """)
        )

        runner = Runner.from_config_file(config_file, profile="dev")
        result = runner.run_task("check_env")

        assert result.success
        assert "development" in result.stdout


class TestRunMultipleTasks:
    """Tests for running multiple tasks."""

    def test_run_multiple_tasks_sequential(self, tmp_path: Path) -> None:
        """Test running multiple tasks sequentially."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.task1]
                cmd = "echo task1"

                [tasks.task2]
                cmd = "echo task2"
            """)
        )

        runner = Runner.from_config_file(config_file)
        results = runner.run_tasks(["task1", "task2"])

        assert len(results) == 2
        assert results["task1"].success
        assert results["task2"].success

    def test_run_multiple_tasks_parallel(self, tmp_path: Path) -> None:
        """Test running multiple tasks in parallel."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.task1]
                cmd = "echo task1"

                [tasks.task2]
                cmd = "echo task2"
            """)
        )

        runner = Runner.from_config_file(config_file)
        results = runner.run_tasks(["task1", "task2"], parallel=True)

        assert len(results) == 2
        assert results["task1"].success
        assert results["task2"].success


class TestBuildCommand:
    """Tests for command building."""

    def test_build_command_basic(self, tmp_path: Path) -> None:
        """Test building basic command."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                script = "test.py"
            """)
        )

        config, _ = load_config(config_file)
        task = config.get_task("test")

        runner = Runner(config=config, project_root=tmp_path, config_path=config_file)
        cmd = runner.build_command(task, "test")

        assert cmd.script == str(tmp_path / "test.py")
        assert cmd.cwd == tmp_path

    def test_build_command_with_dependencies(self, tmp_path: Path) -> None:
        """Test building command with dependencies."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                script = "test.py"
                dependencies = ["pytest>=8.0"]
            """)
        )

        config, _ = load_config(config_file)
        task = config.get_task("test")

        runner = Runner(config=config, project_root=tmp_path, config_path=config_file)
        cmd = runner.build_command(task, "test")

        assert "pytest>=8.0" in cmd.dependencies

    def test_build_command_with_pythonpath(self, tmp_path: Path) -> None:
        """Test building command with PYTHONPATH."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.test]
                script = "test.py"
                pythonpath = ["src"]
            """)
        )

        config, _ = load_config(config_file)
        task = config.get_task("test")

        runner = Runner(config=config, project_root=tmp_path, config_path=config_file)
        cmd = runner.build_command(task, "test")

        # Should have PYTHONPATH in env
        assert "PYTHONPATH" in cmd.env


class TestTaskHooksIntegration:
    """Tests for task hooks integration with runner."""

    def test_run_task_with_before_hook(self, tmp_path: Path) -> None:
        """Test task execution with before_task hook."""
        hook_script = tmp_path / "before.py"
        hook_script.write_text('print("before hook")')

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.main]
                cmd = "echo main"
                before_task = "before.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("main")

        assert result.success

    def test_run_task_with_failing_before_hook(self, tmp_path: Path) -> None:
        """Test that failing before_task hook prevents task execution."""
        hook_script = tmp_path / "before.py"
        hook_script.write_text("import sys; sys.exit(1)")

        marker = tmp_path / "marker.txt"

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent(f"""\
                [project]
                name = "test"

                [tasks.main]
                cmd = "echo main > {marker}"
                before_task = "before.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        result = runner.run_task("main")

        assert result.skipped or not result.success
        assert not marker.exists()


class TestPEP723Integration:
    """Tests for PEP 723 inline dependency support."""

    def test_run_script_with_inline_deps(self, tmp_path: Path) -> None:
        """Test running script with PEP 723 inline dependencies."""
        script = tmp_path / "script.py"
        script.write_text(
            dedent("""\
                # /// script
                # dependencies = [
                #   "rich>=13.0",
                # ]
                # ///

                print("script with deps")
            """)
        )

        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""\
                [project]
                name = "test"

                [tasks.script]
                script = "script.py"
            """)
        )

        runner = Runner.from_config_file(config_file)
        cmd = runner.build_command(runner.config.get_task("script"), "script")

        # Should merge PEP 723 deps with task deps
        assert any("rich" in dep for dep in cmd.dependencies)

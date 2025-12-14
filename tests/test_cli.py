"""Tests for pt CLI commands."""

from pathlib import Path
from textwrap import dedent

import pytest
from click.testing import CliRunner

from uvr.cli import _get_inheritance_chain, _validate_config, main
from uvr.config import load_config


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI runner."""
    return CliRunner()


class TestExplainCommand:
    """Tests for the 'explain' command."""

    def test_explain_simple_task(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a simple task."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.hello]
            description = "Say hello"
            cmd = "echo hello"
        """)
        )

        result = runner.invoke(main, ["explain", "hello", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Task:" in result.output
        assert "hello" in result.output
        assert "Say hello" in result.output
        assert "command" in result.output
        assert "echo hello" in result.output

    def test_explain_task_with_inheritance(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a task with inheritance chain."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.base]
            cmd = "pytest"
            env = { DEBUG = "0" }

            [tasks.test]
            extend = "base"
            description = "Run tests"
            env = { DEBUG = "1" }
        """)
        )

        result = runner.invoke(main, ["explain", "test", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Inheritance:" in result.output
        assert "test → base" in result.output
        assert "DEBUG=1" in result.output

    def test_explain_task_with_depends_on(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a task with dependencies."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.lint]
            cmd = "ruff check"

            [tasks.test]
            cmd = "pytest"

            [tasks.check]
            description = "Run all checks"
            depends_on = ["lint", "test"]
        """)
        )

        result = runner.invoke(main, ["explain", "check", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Task dependencies:" in result.output
        assert "lint" in result.output
        assert "test" in result.output

    def test_explain_task_with_alias(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a task by its alias."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.test]
            description = "Run tests"
            cmd = "pytest"
            aliases = ["t"]
        """)
        )

        result = runner.invoke(main, ["explain", "t", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "test" in result.output
        assert "Aliases:" in result.output

    def test_explain_task_not_found(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a non-existent task."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.hello]
            cmd = "echo hello"
        """)
        )

        result = runner.invoke(main, ["explain", "nonexistent", "-c", str(config_file)])
        assert result.exit_code == 1
        assert "not found" in result.output

    def test_explain_task_with_conditions(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a task with conditions."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.deploy]
            description = "Deploy to production"
            cmd = "deploy.sh"
            condition = { platforms = ["linux"], env_set = ["CI"] }
        """)
        )

        result = runner.invoke(main, ["explain", "deploy", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Conditions:" in result.output
        assert "platforms: linux" in result.output
        assert "env_set: CI" in result.output

    def test_explain_task_with_hooks(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a task with hooks."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.build]
            description = "Build project"
            cmd = "make build"
            before_task = "scripts/setup.py"
            after_success = "scripts/notify.py"
        """)
        )

        result = runner.invoke(main, ["explain", "build", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Hooks:" in result.output
        assert "before_task:" in result.output
        assert "after_success:" in result.output

    def test_explain_task_with_profile(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test explaining a task with a profile."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [env]
            DEBUG = "0"

            [profiles.dev]
            env = { DEBUG = "1" }

            [tasks.run]
            description = "Run app"
            cmd = "python app.py"
        """)
        )

        result = runner.invoke(main, ["explain", "run", "-p", "dev", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "DEBUG=1" in result.output


class TestCheckCommand:
    """Tests for the enhanced 'check' command."""

    def test_check_valid_config(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test checking a valid configuration."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.hello]
            description = "Say hello"
            cmd = "echo hello"
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Configuration valid" in result.output

    def test_check_invalid_depends_on(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test checking config with invalid depends_on reference."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.build]
            description = "Build"
            depends_on = ["nonexistent"]
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 1
        assert "depends on unknown task" in result.output
        assert "nonexistent" in result.output

    def test_check_invalid_pipeline_task(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test checking config with invalid pipeline task reference."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.test]
            description = "Test"
            cmd = "pytest"

            [pipelines.ci]
            stages = [
                { tasks = ["test", "missing"] }
            ]
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 1
        assert "Pipeline 'ci'" in result.output
        assert "unknown task 'missing'" in result.output

    def test_check_invalid_default_profile(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test checking config with invalid default_profile."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"
            default_profile = "nonexistent"

            [tasks.hello]
            description = "Hello"
            cmd = "echo hello"
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 1
        assert "default_profile" in result.output
        assert "not found" in result.output

    def test_check_invalid_on_error_task(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test checking config with invalid on_error_task."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"
            on_error_task = "missing_handler"

            [tasks.hello]
            description = "Hello"
            cmd = "echo hello"
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 1
        assert "on_error_task" in result.output
        assert "not found" in result.output

    def test_check_warning_missing_description(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test warning for tasks without description."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.hello]
            cmd = "echo hello"
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 0  # Warnings don't cause failure
        assert "Warnings:" in result.output
        assert "no description" in result.output

    def test_check_warning_unused_dependency_group(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test warning for unused dependency groups."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [dependencies]
            testing = ["pytest"]
            unused = ["some-package"]

            [tasks.test]
            description = "Run tests"
            cmd = "pytest"
            dependencies = ["testing"]
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "Unused dependency groups" in result.output
        assert "unused" in result.output

    def test_check_warning_variables_without_use_vars(
        self, runner: CliRunner, tmp_path: Path
    ) -> None:
        """Test warning for variables defined but use_vars not enabled."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [variables]
            src_dir = "src"

            [tasks.lint]
            description = "Lint"
            cmd = "ruff check {src_dir}"
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 0
        assert "use_vars is not enabled" in result.output

    def test_check_no_warnings_for_private_tasks(self, runner: CliRunner, tmp_path: Path) -> None:
        """Test that private tasks don't trigger description warnings."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks._private]
            cmd = "echo private"

            [tasks.public]
            description = "Public task"
            cmd = "echo public"
        """)
        )

        result = runner.invoke(main, ["check", "-c", str(config_file)])
        assert result.exit_code == 0
        # Should not warn about _private missing description
        assert "_private" not in result.output or "No issues found" in result.output


class TestValidateConfig:
    """Tests for the _validate_config function."""

    def test_validate_valid_config(self, tmp_path: Path) -> None:
        """Test validation of a valid config."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.test]
            description = "Test"
            cmd = "pytest"
        """)
        )

        config, _ = load_config(config_file)
        issues = _validate_config(config)

        # Should have no errors
        errors = [i for i in issues if i.startswith("[error]")]
        assert len(errors) == 0

    def test_validate_detects_missing_depends_on_task(self, tmp_path: Path) -> None:
        """Test that validation detects missing depends_on tasks."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.build]
            description = "Build"
            depends_on = ["missing"]
        """)
        )

        config, _ = load_config(config_file)
        issues = _validate_config(config)

        errors = [i for i in issues if i.startswith("[error]")]
        assert len(errors) == 1
        assert "depends on unknown task 'missing'" in errors[0]


class TestGetInheritanceChain:
    """Tests for the _get_inheritance_chain function."""

    def test_no_inheritance(self, tmp_path: Path) -> None:
        """Test task with no inheritance."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.hello]
            cmd = "echo hello"
        """)
        )

        config, _ = load_config(config_file)
        chain = _get_inheritance_chain(config, "hello")
        assert chain == ["hello"]

    def test_single_inheritance(self, tmp_path: Path) -> None:
        """Test task with single level inheritance."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.base]
            cmd = "pytest"

            [tasks.test]
            extend = "base"
        """)
        )

        # Load raw config (before inheritance resolution)
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        from uvr.models import UvrConfig

        with config_file.open("rb") as f:
            raw_data = tomllib.load(f)
        raw_config = UvrConfig.model_validate(raw_data)

        chain = _get_inheritance_chain(raw_config, "test")
        assert chain == ["test", "base"]

    def test_deep_inheritance(self, tmp_path: Path) -> None:
        """Test task with multi-level inheritance."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [tasks.base]
            cmd = "pytest"

            [tasks.mid]
            extend = "base"

            [tasks.child]
            extend = "mid"
        """)
        )

        # Load raw config (before inheritance resolution)
        import sys

        if sys.version_info >= (3, 11):
            import tomllib
        else:
            import tomli as tomllib
        from uvr.models import UvrConfig

        with config_file.open("rb") as f:
            raw_data = tomllib.load(f)
        raw_config = UvrConfig.model_validate(raw_data)

        chain = _get_inheritance_chain(raw_config, "child")
        assert chain == ["child", "mid", "base"]

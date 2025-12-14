"""Tests for variable interpolation."""

from pathlib import Path
from textwrap import dedent

import pytest

from uvr.config import apply_variable_interpolation, load_config
from uvr.variables import (
    VariableInterpolationError,
    interpolate_task_fields,
    interpolate_variables,
    merge_variables,
)


class TestInterpolateVariables:
    """Test basic variable interpolation."""

    def test_simple_interpolation(self):
        variables = {"name": "world"}
        result = interpolate_variables("Hello {name}!", variables)
        assert result == "Hello world!"

    def test_multiple_variables(self):
        variables = {"src": "src", "pkg": "myapp"}
        result = interpolate_variables("{src}/{pkg}", variables)
        assert result == "src/myapp"

    def test_recursive_variables(self):
        variables = {"base": "src", "pkg": "myapp", "path": "{base}/{pkg}"}
        result = interpolate_variables("{path}/main.py", variables)
        assert result == "src/myapp/main.py"

    def test_circular_reference_detection(self):
        variables = {"a": "{b}", "b": "{c}", "c": "{a}"}
        with pytest.raises(VariableInterpolationError, match="Circular"):
            interpolate_variables("{a}", variables)

    def test_missing_variable(self):
        variables = {"foo": "bar"}
        with pytest.raises(VariableInterpolationError, match="not found"):
            interpolate_variables("{missing}", variables)

    def test_no_variables(self):
        variables = {}
        result = interpolate_variables("no vars here", variables)
        assert result == "no vars here"

    def test_context_in_error_message(self):
        variables = {}
        with pytest.raises(VariableInterpolationError, match=r"tasks\.test\.cmd.*not found"):
            interpolate_variables("{missing}", variables, context="tasks.test.cmd")


class TestInterpolateTaskFields:
    """Test task field interpolation."""

    def test_interpolate_cmd(self):
        task_dict = {"cmd": "pytest {test_dir}"}
        variables = {"test_dir": "tests"}
        result = interpolate_task_fields(task_dict, variables, "test")
        assert result["cmd"] == "pytest tests"

    def test_interpolate_script(self):
        task_dict = {"script": "scripts/{script_name}.py"}
        variables = {"script_name": "deploy"}
        result = interpolate_task_fields(task_dict, variables, "deploy")
        assert result["script"] == "scripts/deploy.py"

    def test_interpolate_args(self):
        task_dict = {"args": ["{test_dir}", "-v"]}
        variables = {"test_dir": "tests"}
        result = interpolate_task_fields(task_dict, variables, "test")
        assert result["args"] == ["tests", "-v"]

    def test_interpolate_env_values(self):
        task_dict = {"env": {"PATH": "{base}/bin", "NAME": "test"}}
        variables = {"base": "/usr/local"}
        result = interpolate_task_fields(task_dict, variables, "test")
        assert result["env"]["PATH"] == "/usr/local/bin"
        assert result["env"]["NAME"] == "test"

    def test_interpolate_cwd(self):
        task_dict = {"cwd": "{base_dir}/subdir"}
        variables = {"base_dir": "/home/user/project"}
        result = interpolate_task_fields(task_dict, variables, "task")
        assert result["cwd"] == "/home/user/project/subdir"

    def test_interpolate_dependencies(self):
        task_dict = {"dependencies": ["package{version}"]}
        variables = {"version": ">=1.0"}
        result = interpolate_task_fields(task_dict, variables, "task")
        assert result["dependencies"] == ["package>=1.0"]

    def test_interpolate_hooks(self):
        task_dict = {
            "before_task": "scripts/{hook}.py",
            "after_task": "scripts/{after}.py",
        }
        variables = {"hook": "setup", "after": "cleanup"}
        result = interpolate_task_fields(task_dict, variables, "task")
        assert result["before_task"] == "scripts/setup.py"
        assert result["after_task"] == "scripts/cleanup.py"

    def test_none_values_not_interpolated(self):
        task_dict = {"cmd": None, "script": "test.py"}
        variables = {"test": "value"}
        result = interpolate_task_fields(task_dict, variables, "task")
        assert result["cmd"] is None


class TestMergeVariables:
    """Test variable merging."""

    def test_merge_with_profile_override(self):
        global_vars = {"env": "dev", "port": "8000"}
        profile_vars = {"env": "prod"}
        result = merge_variables(global_vars, profile_vars)
        assert result == {"env": "prod", "port": "8000"}

    def test_merge_with_no_profile(self):
        global_vars = {"env": "dev", "port": "8000"}
        result = merge_variables(global_vars, None)
        assert result == {"env": "dev", "port": "8000"}

    def test_merge_with_empty_profile(self):
        global_vars = {"env": "dev"}
        profile_vars = {}
        result = merge_variables(global_vars, profile_vars)
        assert result == {"env": "dev"}


class TestConfigIntegration:
    """Integration tests with full config loading."""

    def test_load_config_with_variables(self, tmp_path: Path):
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            use_vars = true

            [variables]
            test_dir = "tests"
            src_dir = "src"

            [tasks.test]
            cmd = "pytest {test_dir}"

            [tasks.lint]
            cmd = "ruff check {src_dir}"
        """)
        )

        config, _ = load_config(config_file)
        config = apply_variable_interpolation(config)

        assert config.tasks["test"].cmd == "pytest tests"
        assert config.tasks["lint"].cmd == "ruff check src"

    def test_per_task_opt_in(self, tmp_path: Path):
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [variables]
            dir = "mydir"

            [tasks.with_vars]
            use_vars = true
            cmd = "ls {dir}"

            [tasks.without_vars]
            cmd = "ls {dir}"
        """)
        )

        config, _ = load_config(config_file)
        config = apply_variable_interpolation(config)

        assert config.tasks["with_vars"].cmd == "ls mydir"
        assert config.tasks["without_vars"].cmd == "ls {dir}"  # Not interpolated

    def test_profile_variable_override(self, tmp_path: Path):
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            use_vars = true

            [variables]
            env = "dev"

            [profiles.prod]
            variables = { env = "production" }

            [tasks.deploy]
            cmd = "deploy --env {env}"
        """)
        )

        config, _ = load_config(config_file)

        # Test with dev profile (default)
        config_dev = apply_variable_interpolation(config, profile_name=None)
        assert config_dev.tasks["deploy"].cmd == "deploy --env dev"

        # Test with prod profile
        config_prod = apply_variable_interpolation(config, profile_name="prod")
        assert config_prod.tasks["deploy"].cmd == "deploy --env production"

    def test_no_variables_no_interpolation(self, tmp_path: Path):
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [tasks.test]
            cmd = "pytest {test_dir}"
        """)
        )

        config, _ = load_config(config_file)
        config = apply_variable_interpolation(config)

        # No variables defined, so no interpolation
        assert config.tasks["test"].cmd == "pytest {test_dir}"

    def test_complex_variable_substitution(self, tmp_path: Path):
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            use_vars = true

            [variables]
            base = "src"
            package = "myapp"
            module = "core"
            full_path = "{base}/{package}/{module}"

            [tasks.test]
            cmd = "pytest {full_path}"
            env = { PYTHONPATH = "{base}/{package}" }
            args = ["{module}", "-v"]
        """)
        )

        config, _ = load_config(config_file)
        config = apply_variable_interpolation(config)

        task = config.tasks["test"]
        assert task.cmd == "pytest src/myapp/core"
        assert task.env["PYTHONPATH"] == "src/myapp"
        assert task.args == ["core", "-v"]

    def test_variable_in_cwd(self, tmp_path: Path):
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            use_vars = true

            [variables]
            workspace = "workspace"

            [tasks.build]
            cmd = "make"
            cwd = "{workspace}/build"
        """)
        )

        config, _ = load_config(config_file)
        config = apply_variable_interpolation(config)

        assert config.tasks["build"].cwd == "workspace/build"

    def test_escaped_braces(self, tmp_path: Path):
        """Test that double braces are properly escaped."""
        config_file = tmp_path / "uvr.toml"
        config_file.write_text(
            dedent("""
            [project]
            use_vars = true

            [variables]
            var = "value"

            [tasks.test]
            cmd = "echo {var}"
        """)
        )

        config, _ = load_config(config_file)
        config = apply_variable_interpolation(config)

        # Single braces should be interpolated
        assert config.tasks["test"].cmd == "echo value"

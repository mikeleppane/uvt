"""Tests for pt.config."""

from pathlib import Path
from textwrap import dedent

import pytest

from uvtx.config import (
    ConfigError,
    ConfigNotFoundError,
    build_env,
    find_config_file,
    load_config,
    merge_env,
    resolve_path,
)
from uvtx.models import UvrConfig


class TestFindConfigFile:
    """Tests for find_config_file function."""

    def test_find_pt_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "uvt.toml"
        config_file.write_text("[project]\nname = 'test'")

        result = find_config_file(tmp_path)
        assert result == config_file

    def test_find_pyproject_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text("[tool.pt]\n")

        result = find_config_file(tmp_path)
        assert result == config_file

    def test_prefer_pt_toml(self, tmp_path: Path) -> None:
        pt_toml = tmp_path / "uvt.toml"
        pt_toml.write_text("[project]")

        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[tool.pt]")

        result = find_config_file(tmp_path)
        assert result == pt_toml

    def test_find_in_parent(self, tmp_path: Path) -> None:
        config_file = tmp_path / "uvt.toml"
        config_file.write_text("[project]")

        subdir = tmp_path / "subdir" / "nested"
        subdir.mkdir(parents=True)

        result = find_config_file(subdir)
        assert result == config_file

    def test_not_found(self, tmp_path: Path) -> None:
        with pytest.raises(ConfigNotFoundError, match="No pt configuration found"):
            find_config_file(tmp_path)

    def test_pyproject_without_tool_pyr(self, tmp_path: Path) -> None:
        pyproject = tmp_path / "pyproject.toml"
        pyproject.write_text("[project]\nname = 'test'")

        with pytest.raises(ConfigNotFoundError):
            find_config_file(tmp_path)


class TestLoadConfig:
    """Tests for load_config function."""

    def test_load_pyr_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "pyr.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "test"

            [env]
            DEBUG = "1"

            [tasks.hello]
            cmd = "echo hello"
        """)
        )

        config, path = load_config(config_file)
        assert path == config_file
        assert config.project.name == "test"
        assert config.env["DEBUG"] == "1"
        assert "hello" in config.tasks

    def test_load_pyproject_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "pyproject.toml"
        config_file.write_text(
            dedent("""
            [project]
            name = "my-package"

            [tool.pyr]
            [tool.pyr.tasks.test]
            cmd = "pytest"
        """)
        )

        config, path = load_config(config_file)
        assert path == config_file
        assert "test" in config.tasks

    def test_invalid_toml(self, tmp_path: Path) -> None:
        config_file = tmp_path / "pyr.toml"
        config_file.write_text("invalid = [")

        with pytest.raises(ConfigError, match="Invalid TOML"):
            load_config(config_file)

    def test_invalid_config_schema(self, tmp_path: Path) -> None:
        config_file = tmp_path / "pyr.toml"
        config_file.write_text(
            dedent("""
            [tasks.invalid]
            # Missing script, cmd, and depends_on
            description = "Invalid task"
        """)
        )

        with pytest.raises(ConfigError, match="Invalid configuration"):
            load_config(config_file)


class TestBuildEnv:
    """Tests for build_env function."""

    def test_simple_values(self, tmp_path: Path) -> None:
        config = UvrConfig(env={"DEBUG": "1", "LOG_LEVEL": "info"})
        env = build_env(config, tmp_path)
        assert env["DEBUG"] == "1"
        assert env["LOG_LEVEL"] == "info"

    def test_list_values_joined(self, tmp_path: Path) -> None:
        config = UvrConfig(env={"PYTHONPATH": ["src", "lib"]})
        env = build_env(config, tmp_path)

        import os

        expected = os.pathsep.join(
            [
                str(tmp_path / "src"),
                str(tmp_path / "lib"),
            ]
        )
        assert env["PYTHONPATH"] == expected

    def test_paths_resolved(self, tmp_path: Path) -> None:
        config = UvrConfig(env={"PYTHONPATH": ["./src"]})
        env = build_env(config, tmp_path)

        assert str(tmp_path / "src") in env["PYTHONPATH"]


class TestMergeEnv:
    """Tests for merge_env function."""

    def test_merge_simple(self) -> None:
        env1 = {"A": "1", "B": "2"}
        env2 = {"B": "3", "C": "4"}
        result = merge_env(env1, env2)
        assert result == {"A": "1", "B": "3", "C": "4"}

    def test_merge_pythonpath(self, tmp_path: Path) -> None:
        import os

        env1 = {"PYTHONPATH": f"src{os.pathsep}lib"}
        env2 = {"OTHER": "value"}

        result = merge_env(
            env1,
            env2,
            pythonpath_lists=[["tests"]],
            project_root=tmp_path,
        )

        assert "PYTHONPATH" in result
        assert "src" in result["PYTHONPATH"]
        assert "lib" in result["PYTHONPATH"]
        assert str(tmp_path / "tests") in result["PYTHONPATH"]


class TestResolvePath:
    """Tests for resolve_path function."""

    def test_relative_path(self, tmp_path: Path) -> None:
        result = resolve_path("src/module", tmp_path)
        assert result == (tmp_path / "src" / "module").resolve()

    def test_absolute_path(self, tmp_path: Path) -> None:
        abs_path = "/absolute/path"
        result = resolve_path(abs_path, tmp_path)
        assert result == Path(abs_path)

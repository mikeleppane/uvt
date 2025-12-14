"""Tests for task aliasing feature."""

import textwrap
from pathlib import Path

import pytest

from uvtx.config import ConfigError, load_config, resolve_task_name


def test_alias_resolution_by_name(tmp_path: Path) -> None:
    """Test that task names resolve to themselves."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t", "tests"]
        """)
    )

    config, _ = load_config(config_file)
    assert resolve_task_name(config, "test") == "test"


def test_alias_resolution_by_alias(tmp_path: Path) -> None:
    """Test that aliases resolve to task names."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t", "tests"]
        """)
    )

    config, _ = load_config(config_file)
    assert resolve_task_name(config, "t") == "test"
    assert resolve_task_name(config, "tests") == "test"


def test_alias_resolution_unknown_task(tmp_path: Path) -> None:
    """Test that unknown tasks raise ValueError with suggestions."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t"]
        """)
    )

    config, _ = load_config(config_file)
    with pytest.raises(ValueError, match="Task or alias 'unknown' not found"):
        resolve_task_name(config, "unknown")


def test_duplicate_alias_rejected(tmp_path: Path) -> None:
    """Test that duplicate aliases are rejected."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t"]

            [tasks.build]
            cmd = "python -m build"
            aliases = ["t"]  # Duplicate!
        """)
    )

    with pytest.raises(ConfigError, match="Duplicate alias 't'"):
        load_config(config_file)


def test_alias_conflicts_with_task_name(tmp_path: Path) -> None:
    """Test that alias cannot conflict with task name."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"

            [tasks.build]
            cmd = "python -m build"
            aliases = ["test"]  # Conflicts with task name!
        """)
    )

    with pytest.raises(ConfigError, match="Alias 'test' conflicts with task name"):
        load_config(config_file)


def test_multiple_aliases_same_task(tmp_path: Path) -> None:
    """Test that multiple aliases can point to the same task."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t", "tests", "unittest"]
        """)
    )

    config, _ = load_config(config_file)
    assert resolve_task_name(config, "t") == "test"
    assert resolve_task_name(config, "tests") == "test"
    assert resolve_task_name(config, "unittest") == "test"


def test_aliases_across_multiple_tasks(tmp_path: Path) -> None:
    """Test that aliases work across multiple tasks."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t"]

            [tasks.lint]
            cmd = "ruff check"
            aliases = ["l"]

            [tasks.build]
            cmd = "python -m build"
            aliases = ["b"]
        """)
    )

    config, _ = load_config(config_file)
    assert resolve_task_name(config, "t") == "test"
    assert resolve_task_name(config, "l") == "lint"
    assert resolve_task_name(config, "b") == "build"


def test_alias_in_depends_on(tmp_path: Path) -> None:
    """Test that aliases work in depends_on field."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.lint]
            cmd = "ruff check"
            aliases = ["l"]

            [tasks.test]
            cmd = "pytest"
            depends_on = ["l"]  # Uses alias
        """)
    )

    config, _ = load_config(config_file)
    # Should load without error
    assert "test" in config.tasks
    assert "lint" in config.tasks


def test_empty_aliases_list(tmp_path: Path) -> None:
    """Test that empty aliases list is valid."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = []
        """)
    )

    config, _ = load_config(config_file)
    assert config.tasks["test"].aliases == []


def test_task_without_aliases(tmp_path: Path) -> None:
    """Test that tasks without aliases work normally."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
        """)
    )

    config, _ = load_config(config_file)
    assert resolve_task_name(config, "test") == "test"
    assert config.tasks["test"].aliases == []


def test_get_task_by_alias(tmp_path: Path) -> None:
    """Test that get_task works with aliases."""
    config_file = tmp_path / "uvt.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            aliases = ["t"]
        """)
    )

    config, _ = load_config(config_file)
    task_by_name = config.get_task("test")
    task_by_alias = config.get_task("t")
    assert task_by_name is task_by_alias

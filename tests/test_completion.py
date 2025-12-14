"""Tests for shell completion."""

from pathlib import Path
from textwrap import dedent
from unittest.mock import Mock

import pytest

from pt.completion import (
    complete_pipeline_name,
    complete_profile_name,
    complete_task_name,
)


def test_complete_task_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test task name completion returns task names and aliases."""
    # Create test config
    config_file = tmp_path / "pt.toml"
    config_file.write_text(
        dedent("""
        [project]
        name = "test"

        [tasks.test]
        description = "Run tests"
        cmd = "pytest"

        [tasks.lint]
        description = "Run linting"
        cmd = "ruff check"
        aliases = ["l"]

        [tasks._private]
        description = "Private task"
        cmd = "echo private"
        """)
    )

    # Change to test directory
    monkeypatch.chdir(tmp_path)

    # Mock context
    ctx = Mock()
    param = Mock()

    # Test completion
    results = complete_task_name(ctx, param, "")
    result_values = [r.value for r in results]

    # Should include public tasks and aliases, not private tasks
    assert "test" in result_values
    assert "lint" in result_values
    assert "l" in result_values
    assert "_private" not in result_values


def test_complete_task_names_with_incomplete(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test task name completion filters by incomplete string."""
    config_file = tmp_path / "pt.toml"
    config_file.write_text(
        dedent("""
        [project]
        name = "test"

        [tasks.test]
        cmd = "pytest"

        [tasks.lint]
        cmd = "ruff"

        [tasks.format]
        cmd = "ruff format"
        """)
    )

    monkeypatch.chdir(tmp_path)

    ctx = Mock()
    param = Mock()

    # Test filtering
    results = complete_task_name(ctx, param, "te")
    result_values = [r.value for r in results]

    assert "test" in result_values
    assert "lint" not in result_values
    assert "format" not in result_values


def test_complete_profile_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test profile name completion."""
    config_file = tmp_path / "pt.toml"
    config_file.write_text(
        dedent("""
        [project]
        name = "test"

        [profiles.dev]
        env = { DEBUG = "1" }

        [profiles.ci]
        env = { CI = "1" }

        [profiles.prod]
        env = { PRODUCTION = "1" }
        """)
    )

    monkeypatch.chdir(tmp_path)

    ctx = Mock()
    param = Mock()

    results = complete_profile_name(ctx, param, "")
    result_values = [r.value for r in results]

    assert "dev" in result_values
    assert "ci" in result_values
    assert "prod" in result_values


def test_complete_pipeline_names(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    """Test pipeline name completion."""
    config_file = tmp_path / "pt.toml"
    config_file.write_text(
        dedent("""
        [project]
        name = "test"

        [tasks.test]
        cmd = "pytest"

        [tasks.lint]
        cmd = "ruff"

        [pipelines.ci]
        description = "CI pipeline"
        stages = [
            { tasks = ["lint", "test"] }
        ]

        [pipelines.deploy]
        description = "Deployment pipeline"
        stages = [
            { tasks = ["test"] }
        ]
        """)
    )

    monkeypatch.chdir(tmp_path)

    ctx = Mock()
    param = Mock()

    results = complete_pipeline_name(ctx, param, "")
    result_values = [r.value for r in results]

    assert "ci" in result_values
    assert "deploy" in result_values


def test_complete_with_no_config() -> None:
    """Test completion gracefully handles missing config."""
    ctx = Mock()
    param = Mock()

    # Should not raise, return empty list
    results = complete_task_name(ctx, param, "test")
    assert results == []

    results = complete_profile_name(ctx, param, "dev")
    assert results == []

    results = complete_pipeline_name(ctx, param, "ci")
    assert results == []


def test_complete_task_with_aliases_description(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Test that aliases show helpful descriptions."""
    config_file = tmp_path / "pt.toml"
    config_file.write_text(
        dedent("""
        [project]
        name = "test"

        [tasks.lint]
        description = "Run linting"
        cmd = "ruff"
        aliases = ["l", "check"]
        """)
    )

    monkeypatch.chdir(tmp_path)

    ctx = Mock()
    param = Mock()

    results = complete_task_name(ctx, param, "")

    # Find the alias completion item
    alias_items = [r for r in results if r.value in ["l", "check"]]
    assert len(alias_items) == 2

    # Check that alias items have helpful descriptions
    for item in alias_items:
        assert "Alias for lint" in item.help

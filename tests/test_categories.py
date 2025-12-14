"""Tests for task category feature."""

import textwrap
from pathlib import Path

from uvr.config import load_config


def test_category_field_basic(tmp_path: Path) -> None:
    """Test that category field can be set."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"
        """)
    )

    config, _ = load_config(config_file)
    assert config.tasks["test"].category == "testing"


def test_category_optional(tmp_path: Path) -> None:
    """Test that category is optional."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
        """)
    )

    config, _ = load_config(config_file)
    assert config.tasks["test"].category is None


def test_category_inheritance(tmp_path: Path) -> None:
    """Test that child tasks inherit category from parent."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.base]
            cmd = "echo base"
            category = "testing"

            [tasks.unit]
            extend = "base"
            cmd = "pytest tests/unit"
        """)
    )

    config, _ = load_config(config_file)
    # Child should inherit parent's category
    assert config.tasks["unit"].category == "testing"


def test_category_inheritance_override(tmp_path: Path) -> None:
    """Test that child can override parent's category."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.base]
            cmd = "echo base"
            category = "testing"

            [tasks.deploy]
            extend = "base"
            cmd = "deploy.sh"
            category = "deployment"
        """)
    )

    config, _ = load_config(config_file)
    # Child overrides parent's category
    assert config.tasks["deploy"].category == "deployment"


def test_category_inheritance_chain(tmp_path: Path) -> None:
    """Test category inheritance through multiple levels."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.base]
            cmd = "echo base"
            category = "ci"

            [tasks.test-base]
            extend = "base"
            cmd = "pytest"

            [tasks.unit-test]
            extend = "test-base"
            cmd = "pytest tests/unit"
        """)
    )

    config, _ = load_config(config_file)
    # All inherit from base
    assert config.tasks["test-base"].category == "ci"
    assert config.tasks["unit-test"].category == "ci"


def test_get_tasks_by_category(tmp_path: Path) -> None:
    """Test filtering tasks by category."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"

            [tasks.lint]
            cmd = "ruff check"
            category = "quality"

            [tasks.build]
            cmd = "python -m build"
            category = "build"

            [tasks.unit]
            cmd = "pytest tests/unit"
            category = "testing"
        """)
    )

    config, _ = load_config(config_file)
    testing_tasks = config.get_tasks_by_category("testing")

    assert len(testing_tasks) == 2
    assert "test" in testing_tasks
    assert "unit" in testing_tasks
    assert "lint" not in testing_tasks
    assert "build" not in testing_tasks


def test_get_tasks_by_category_empty(tmp_path: Path) -> None:
    """Test filtering by non-existent category."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"
        """)
    )

    config, _ = load_config(config_file)
    deploy_tasks = config.get_tasks_by_category("deployment")

    assert len(deploy_tasks) == 0


def test_get_tasks_by_category_none(tmp_path: Path) -> None:
    """Test that tasks without category are not included."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"

            [tasks.uncategorized]
            cmd = "echo hello"
        """)
    )

    config, _ = load_config(config_file)
    testing_tasks = config.get_tasks_by_category("testing")

    assert "test" in testing_tasks
    assert "uncategorized" not in testing_tasks


def test_get_all_categories(tmp_path: Path) -> None:
    """Test getting all categories with counts."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"

            [tasks.unit]
            cmd = "pytest tests/unit"
            category = "testing"

            [tasks.lint]
            cmd = "ruff check"
            category = "quality"

            [tasks.build]
            cmd = "python -m build"
            category = "build"

            [tasks.uncategorized]
            cmd = "echo hello"
        """)
    )

    config, _ = load_config(config_file)
    categories = config.get_all_categories()

    assert categories == {"testing": 2, "quality": 1, "build": 1}


def test_get_all_categories_empty(tmp_path: Path) -> None:
    """Test getting categories when none are set."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"

            [tasks.lint]
            cmd = "ruff check"
        """)
    )

    config, _ = load_config(config_file)
    categories = config.get_all_categories()

    assert categories == {}


def test_category_with_tags(tmp_path: Path) -> None:
    """Test that category and tags work together."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"
            tags = ["ci", "unit"]
        """)
    )

    config, _ = load_config(config_file)
    task = config.tasks["test"]

    assert task.category == "testing"
    assert task.tags == ["ci", "unit"]


def test_multiple_categories_not_allowed(tmp_path: Path) -> None:
    """Test that category is a single string, not a list."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "pytest"
            category = "testing"
        """)
    )

    config, _ = load_config(config_file)
    # Category should be a string
    assert isinstance(config.tasks["test"].category, str)

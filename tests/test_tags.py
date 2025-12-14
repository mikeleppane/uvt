"""Tests for task tags."""

from pathlib import Path
from textwrap import dedent

import pytest

from uvtx.config import load_config
from uvtx.models import UvrConfig


class TestTagValidation:
    """Tests for tag validation."""

    def test_valid_tags(self, tmp_path: Path) -> None:
        """Test that valid tags are accepted."""
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
            tags = ["ci", "fast", "pre-commit", "unit_test"]
            """)
        )

        config, _ = load_config(config_file)
        assert config.tasks["test"].tags == ["ci", "fast", "pre-commit", "unit_test"]

    def test_empty_tag_rejected(self, tmp_path: Path) -> None:
        """Test that empty tags are rejected."""
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
            tags = ["ci", ""]
            """)
        )

        with pytest.raises(Exception, match="Tag cannot be empty"):
            load_config(config_file)

    def test_invalid_tag_characters(self, tmp_path: Path) -> None:
        """Test that tags with invalid characters are rejected."""
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
            tags = ["ci", "tag with spaces"]
            """)
        )

        with pytest.raises(Exception, match="must be alphanumeric"):
            load_config(config_file)


class TestTagInheritance:
    """Tests for tag inheritance via extend."""

    def test_tags_are_merged_and_deduplicated(self, tmp_path: Path) -> None:
        """Test that child tags are merged with parent tags."""
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.base]
            cmd = "pytest"
            tags = ["testing", "ci"]

            [tasks.unit]
            extend = "base"
            args = ["tests/unit"]
            tags = ["fast", "ci"]  # "ci" is duplicate, should be deduplicated
            """)
        )

        config, _ = load_config(config_file)
        # Tags should be merged and sorted
        assert set(config.tasks["unit"].tags) == {"testing", "ci", "fast"}
        # Tags should be sorted
        assert config.tasks["unit"].tags == sorted(["testing", "ci", "fast"])

    def test_tags_inheritance_chain(self, tmp_path: Path) -> None:
        """Test tag inheritance through multiple levels."""
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.base]
            cmd = "pytest"
            tags = ["testing"]

            [tasks.integration]
            extend = "base"
            tags = ["slow"]

            [tasks.e2e]
            extend = "integration"
            tags = ["ci", "deployment"]
            """)
        )

        config, _ = load_config(config_file)
        # Should have all tags from the chain
        assert set(config.tasks["e2e"].tags) == {"testing", "slow", "ci", "deployment"}


class TestTagFiltering:
    """Tests for filtering tasks by tags."""

    def setup_config(self, tmp_path: Path) -> UvrConfig:
        """Create a test config with tagged tasks."""
        config_file = tmp_path / "uvt.toml"
        config_file.write_text(
            dedent("""\
            [project]
            name = "test"

            [tasks.lint]
            cmd = "ruff check"
            tags = ["ci", "quality", "fast"]

            [tasks.test-unit]
            cmd = "pytest tests/unit"
            tags = ["ci", "testing", "fast"]

            [tasks.test-integration]
            cmd = "pytest tests/integration"
            tags = ["ci", "testing", "slow"]

            [tasks.deploy]
            cmd = "deploy.sh"
            tags = ["production", "dangerous"]

            [tasks.format]
            cmd = "ruff format"
            tags = ["quality"]
            """)
        )

        config, _ = load_config(config_file)
        return config

    def test_get_tasks_by_single_tag(self, tmp_path: Path) -> None:
        """Test filtering tasks by a single tag."""
        config = self.setup_config(tmp_path)

        ci_tasks = config.get_tasks_by_tag("ci")
        assert set(ci_tasks.keys()) == {"lint", "test-unit", "test-integration"}

        quality_tasks = config.get_tasks_by_tag("quality")
        assert set(quality_tasks.keys()) == {"lint", "format"}

        production_tasks = config.get_tasks_by_tag("production")
        assert set(production_tasks.keys()) == {"deploy"}

    def test_get_tasks_by_multiple_tags_match_all(self, tmp_path: Path) -> None:
        """Test filtering tasks by multiple tags with AND logic."""
        config = self.setup_config(tmp_path)

        # Tasks with both "ci" AND "fast"
        tasks = config.get_tasks_by_tags(["ci", "fast"], match_all=True)
        assert set(tasks.keys()) == {"lint", "test-unit"}

        # Tasks with both "ci" AND "slow"
        tasks = config.get_tasks_by_tags(["ci", "slow"], match_all=True)
        assert set(tasks.keys()) == {"test-integration"}

        # No tasks have all three tags
        tasks = config.get_tasks_by_tags(["ci", "quality", "slow"], match_all=True)
        assert len(tasks) == 0

    def test_get_tasks_by_multiple_tags_match_any(self, tmp_path: Path) -> None:
        """Test filtering tasks by multiple tags with OR logic."""
        config = self.setup_config(tmp_path)

        # Tasks with either "fast" OR "slow"
        tasks = config.get_tasks_by_tags(["fast", "slow"], match_all=False)
        assert set(tasks.keys()) == {"lint", "test-unit", "test-integration"}

        # Tasks with either "production" OR "dangerous"
        tasks = config.get_tasks_by_tags(["production", "dangerous"], match_all=False)
        assert set(tasks.keys()) == {"deploy"}

    def test_get_all_tags(self, tmp_path: Path) -> None:
        """Test getting all unique tags across all tasks."""
        config = self.setup_config(tmp_path)

        all_tags = config.get_all_tags()
        assert all_tags == {
            "ci",
            "quality",
            "fast",
            "testing",
            "slow",
            "production",
            "dangerous",
        }

    def test_get_tasks_by_nonexistent_tag(self, tmp_path: Path) -> None:
        """Test that filtering by non-existent tag returns empty dict."""
        config = self.setup_config(tmp_path)

        tasks = config.get_tasks_by_tag("nonexistent")
        assert tasks == {}

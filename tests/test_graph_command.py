"""Tests for graph visualization command."""

from __future__ import annotations

from textwrap import dedent
from typing import TYPE_CHECKING

from click.testing import CliRunner

from uvtx.cli import main

if TYPE_CHECKING:
    from pathlib import Path


class TestGraphCommand:
    """Test graph visualization command."""

    def test_graph_simple_task(self, tmp_path: Path) -> None:
        """Test graph visualization for a simple task."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.build]
            cmd = "echo build"

            [tasks.test]
            cmd = "echo test"
            depends_on = ["build"]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "test", "-c", str(config_path)])

        assert result.exit_code == 0
        assert "test" in result.output
        assert "build" in result.output

    def test_graph_ascii_format(self, tmp_path: Path) -> None:
        """Test ASCII tree format."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.lint]
            cmd = "echo lint"

            [tasks.test]
            cmd = "echo test"

            [tasks.ci]
            cmd = "echo ci"
            depends_on = ["lint", "test"]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "ci", "--format", "ascii", "-c", str(config_path)])

        assert result.exit_code == 0
        # Should show tree structure
        assert "ci" in result.output
        assert "lint" in result.output
        assert "test" in result.output
        # Check for tree characters
        assert "├──" in result.output or "└──" in result.output

    def test_graph_dot_format(self, tmp_path: Path) -> None:
        """Test DOT (Graphviz) format."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.build]
            cmd = "echo build"

            [tasks.deploy]
            cmd = "echo deploy"
            depends_on = ["build"]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "--format", "dot", "-c", str(config_path)])

        assert result.exit_code == 0
        assert "digraph tasks" in result.output
        assert '"deploy"' in result.output
        assert '"build"' in result.output
        assert "->" in result.output

    def test_graph_mermaid_format(self, tmp_path: Path) -> None:
        """Test Mermaid diagram format."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.lint]
            cmd = "echo lint"

            [tasks.test]
            cmd = "echo test"
            depends_on = ["lint"]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "--format", "mermaid", "-c", str(config_path)])

        assert result.exit_code == 0
        assert "graph TD" in result.output
        assert "test" in result.output
        assert "lint" in result.output
        assert "-->" in result.output

    def test_graph_output_to_file(self, tmp_path: Path) -> None:
        """Test writing graph to a file."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.build]
            cmd = "echo build"
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        output_file = tmp_path / "graph.dot"

        runner = CliRunner()
        result = runner.invoke(
            main,
            ["graph", "--format", "dot", "-o", str(output_file), "-c", str(config_path)],
        )

        assert result.exit_code == 0
        assert output_file.exists()
        content = output_file.read_text()
        assert "digraph tasks" in content
        assert "build" in content

    def test_graph_all_tasks(self, tmp_path: Path) -> None:
        """Test graph without specific task shows all tasks."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.task1]
            cmd = "echo 1"

            [tasks.task2]
            cmd = "echo 2"

            [tasks.task3]
            cmd = "echo 3"
            depends_on = ["task1", "task2"]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "-c", str(config_path)])

        assert result.exit_code == 0
        assert "task1" in result.output
        assert "task2" in result.output
        assert "task3" in result.output

    def test_graph_complex_dependencies(self, tmp_path: Path) -> None:
        """Test graph with complex dependency chain."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.format]
            cmd = "echo format"

            [tasks.lint]
            cmd = "echo lint"
            depends_on = ["format"]

            [tasks.test]
            cmd = "echo test"

            [tasks.ci]
            cmd = "echo ci"
            depends_on = ["lint", "test"]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "ci", "--format", "ascii", "-c", str(config_path)])

        assert result.exit_code == 0
        # All dependencies should appear
        assert "ci" in result.output
        assert "lint" in result.output
        assert "test" in result.output
        assert "format" in result.output

    def test_graph_unknown_task(self, tmp_path: Path) -> None:
        """Test graph with unknown task name."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.build]
            cmd = "echo build"
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "nonexistent", "-c", str(config_path)])

        assert result.exit_code == 1
        assert "not found" in result.output.lower()

    def test_graph_no_dependencies(self, tmp_path: Path) -> None:
        """Test graph for task with no dependencies."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.standalone]
            cmd = "echo standalone"
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = CliRunner()
        result = runner.invoke(main, ["graph", "standalone", "-c", str(config_path)])

        assert result.exit_code == 0
        assert "standalone" in result.output

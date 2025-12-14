"""Tests for pt.graph."""

import pytest

from uvtx.graph import (
    CycleError,
    TaskGraph,
    UnknownTaskError,
    build_task_graph,
)
from uvtx.models import TaskConfig, UvrConfig


class TestTaskGraph:
    """Tests for TaskGraph class."""

    def test_empty_graph(self) -> None:
        graph = TaskGraph()
        assert graph.topological_sort() == []

    def test_single_node(self) -> None:
        graph = TaskGraph()
        graph.add_node("task1", TaskConfig(cmd="echo 1"))
        result = graph.topological_sort()
        assert result == ["task1"]

    def test_linear_dependencies(self) -> None:
        graph = TaskGraph()
        graph.add_node("a", TaskConfig(cmd="a"))
        graph.add_node("b", TaskConfig(cmd="b"))
        graph.add_node("c", TaskConfig(cmd="c"))
        graph.add_edge("c", "b")  # c depends on b
        graph.add_edge("b", "a")  # b depends on a

        result = graph.topological_sort()
        # a should come before b, b before c
        assert result.index("a") < result.index("b")
        assert result.index("b") < result.index("c")

    def test_parallel_dependencies(self) -> None:
        graph = TaskGraph()
        graph.add_node("test", TaskConfig(cmd="test"))
        graph.add_node("lint", TaskConfig(cmd="lint"))
        graph.add_node("typecheck", TaskConfig(cmd="typecheck"))
        graph.add_node("check", TaskConfig(depends_on=["lint", "typecheck", "test"]))

        graph.add_edge("check", "lint")
        graph.add_edge("check", "typecheck")
        graph.add_edge("check", "test")

        result = graph.topological_sort()
        # All deps should come before check
        assert result.index("lint") < result.index("check")
        assert result.index("typecheck") < result.index("check")
        assert result.index("test") < result.index("check")

    def test_cycle_detection(self) -> None:
        graph = TaskGraph()
        graph.add_node("a", TaskConfig(cmd="a"))
        graph.add_node("b", TaskConfig(cmd="b"))
        graph.add_node("c", TaskConfig(cmd="c"))

        graph.add_edge("a", "b")
        graph.add_edge("b", "c")
        graph.add_edge("c", "a")  # Creates cycle

        with pytest.raises(CycleError) as exc_info:
            graph.topological_sort()
        assert "Circular dependency" in str(exc_info.value)

    def test_get_dependencies(self) -> None:
        graph = TaskGraph()
        graph.add_node("a", TaskConfig(cmd="a"))
        graph.add_node("b", TaskConfig(cmd="b"))
        graph.add_edge("a", "b")

        assert graph.get_dependencies("a") == {"b"}
        assert graph.get_dependencies("b") == set()

    def test_get_all_dependencies(self) -> None:
        graph = TaskGraph()
        graph.add_node("a", TaskConfig(cmd="a"))
        graph.add_node("b", TaskConfig(cmd="b"))
        graph.add_node("c", TaskConfig(cmd="c"))

        graph.add_edge("c", "b")
        graph.add_edge("b", "a")

        assert graph.get_all_dependencies("c") == {"a", "b"}
        assert graph.get_all_dependencies("b") == {"a"}
        assert graph.get_all_dependencies("a") == set()

    def test_execution_levels(self) -> None:
        graph = TaskGraph()
        graph.add_node("a", TaskConfig(cmd="a"))
        graph.add_node("b", TaskConfig(cmd="b"))
        graph.add_node("c", TaskConfig(cmd="c"))
        graph.add_node("d", TaskConfig(cmd="d"))

        # d depends on b and c, which both depend on a
        graph.add_edge("d", "b")
        graph.add_edge("d", "c")
        graph.add_edge("b", "a")
        graph.add_edge("c", "a")

        levels = graph.get_execution_levels()

        # Level 0: a (no deps)
        # Level 1: b, c (depend on a)
        # Level 2: d (depends on b, c)
        assert len(levels) == 3
        assert levels[0] == ["a"]
        assert set(levels[1]) == {"b", "c"}
        assert levels[2] == ["d"]


class TestBuildTaskGraph:
    """Tests for build_task_graph function."""

    def test_single_task(self) -> None:
        config = UvrConfig(tasks={"test": TaskConfig(cmd="pytest")})
        graph = build_task_graph(config, ["test"])
        assert "test" in graph.nodes

    def test_with_dependencies(self) -> None:
        config = UvrConfig(
            tasks={
                "lint": TaskConfig(cmd="ruff"),
                "test": TaskConfig(cmd="pytest"),
                "check": TaskConfig(depends_on=["lint", "test"]),
            }
        )
        graph = build_task_graph(config, ["check"])

        assert "check" in graph.nodes
        assert "lint" in graph.nodes
        assert "test" in graph.nodes

    def test_unknown_dependency(self) -> None:
        config = UvrConfig(
            tasks={
                "task": TaskConfig(depends_on=["nonexistent"]),
            }
        )
        with pytest.raises(UnknownTaskError, match="nonexistent"):
            build_task_graph(config, ["task"])

    def test_unknown_task(self) -> None:
        config = UvrConfig()
        with pytest.raises(KeyError, match="not found"):
            build_task_graph(config, ["nonexistent"])

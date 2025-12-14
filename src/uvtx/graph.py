"""Task dependency graph with topological sorting and cycle detection."""

from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from collections.abc import Iterator

    from uvtx.models import TaskConfig, UvrConfig


class CycleError(Exception):
    """Raised when a cycle is detected in the task dependency graph."""

    def __init__(self, cycle: list[str]) -> None:
        self.cycle = cycle
        cycle_str = " -> ".join([*cycle, cycle[0]])
        super().__init__(f"Circular dependency detected: {cycle_str}")


class UnknownTaskError(Exception):
    """Raised when a task references an unknown dependency."""

    def __init__(self, task: str, dependency: str) -> None:
        self.task = task
        self.dependency = dependency
        super().__init__(f"Task '{task}' depends on unknown task '{dependency}'")


@dataclass
class TaskNode:
    """A node in the task dependency graph."""

    name: str
    config: TaskConfig
    args_override: list[str] = field(default_factory=list)

    def __hash__(self) -> int:
        return hash(self.name)

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, TaskNode):
            return NotImplemented
        return self.name == other.name


@dataclass
class TaskGraph:
    """Directed acyclic graph of task dependencies."""

    nodes: dict[str, TaskNode] = field(default_factory=dict)
    edges: dict[str, set[str]] = field(default_factory=lambda: defaultdict(set))

    def add_node(
        self, name: str, config: TaskConfig, args_override: list[str] | None = None
    ) -> None:
        """Add a task node to the graph."""
        if name not in self.nodes:
            self.nodes[name] = TaskNode(name=name, config=config, args_override=args_override or [])

    def add_edge(self, from_task: str, to_task: str) -> None:
        """Add a dependency edge (from_task depends on to_task)."""
        self.edges[from_task].add(to_task)

    def get_dependencies(self, task: str) -> set[str]:
        """Get direct dependencies of a task."""
        return self.edges.get(task, set())

    def get_all_dependencies(self, task: str) -> set[str]:
        """Get all transitive dependencies of a task."""
        result: set[str] = set()
        stack = list(self.get_dependencies(task))

        while stack:
            dep = stack.pop()
            if dep not in result:
                result.add(dep)
                stack.extend(self.get_dependencies(dep))

        return result

    def topological_sort(self) -> list[str]:
        """Return tasks in topological order (dependencies first).

        Raises:
            CycleError: If a cycle is detected.
        """
        # Kahn's algorithm
        in_degree: dict[str, int] = dict.fromkeys(self.nodes, 0)

        for deps in self.edges.values():
            for dep in deps:
                if dep in in_degree:
                    in_degree[dep] += 1

        # Start with nodes that have no dependencies
        queue = [name for name, degree in in_degree.items() if degree == 0]
        result: list[str] = []

        while queue:
            # Sort for deterministic ordering
            queue.sort()
            node = queue.pop(0)
            result.append(node)

            for dep in self.edges.get(node, set()):
                if dep in in_degree:
                    in_degree[dep] -= 1
                    if in_degree[dep] == 0:
                        queue.append(dep)

        if len(result) != len(self.nodes):
            # Cycle detected - find it for error message
            cycle = self._find_cycle()
            raise CycleError(cycle)

        # Reverse to get dependencies first
        return list(reversed(result))

    def _find_cycle(self) -> list[str]:
        """Find a cycle in the graph for error reporting."""
        visited: set[str] = set()
        rec_stack: set[str] = set()
        path: list[str] = []

        def dfs(node: str) -> list[str] | None:
            visited.add(node)
            rec_stack.add(node)
            path.append(node)

            for neighbor in self.edges.get(node, set()):
                if neighbor not in visited:
                    result = dfs(neighbor)
                    if result:
                        return result
                elif neighbor in rec_stack:
                    # Found cycle
                    cycle_start = path.index(neighbor)
                    return path[cycle_start:]

            path.pop()
            rec_stack.remove(node)
            return None

        for node in self.nodes:
            if node not in visited:
                cycle = dfs(node)
                if cycle:
                    return cycle

        return []

    def get_execution_levels(self) -> list[list[str]]:
        """Group tasks into levels for parallel execution.

        Tasks in the same level can be executed in parallel.
        Returns levels in execution order (earlier levels first).
        """
        sorted_tasks = self.topological_sort()
        levels: list[list[str]] = []
        task_level: dict[str, int] = {}

        for task in sorted_tasks:
            deps = self.get_dependencies(task)
            level = 0 if not deps else max(task_level.get(d, 0) for d in deps) + 1
            task_level[task] = level

            while len(levels) <= level:
                levels.append([])
            levels[level].append(task)

        return levels

    def __iter__(self) -> Iterator[TaskNode]:
        """Iterate over nodes in topological order."""
        for name in self.topological_sort():
            yield self.nodes[name]


def build_task_graph(
    config: UvrConfig,
    task_names: list[str],
) -> TaskGraph:
    """Build a task graph from configuration.

    Args:
        config: The pyr configuration.
        task_names: Names of tasks to include (with their dependencies).

    Returns:
        TaskGraph with all required tasks and dependencies.

    Raises:
        UnknownTaskError: If a task references an unknown dependency.
    """
    from uvtx.config import resolve_task_name

    graph = TaskGraph()

    def add_task_recursive(
        name: str,
        args_override: list[str] | None = None,
    ) -> None:
        if name in graph.nodes:
            return

        task_config = config.get_task(name)
        graph.add_node(name, task_config, args_override)

        for dep in task_config.depends_on:
            dep_name: str
            dep_args: list[str] = []

            if isinstance(dep, str):
                dep_name = dep
            else:
                # TaskDependency object
                dep_name = dep.task
                dep_args = dep.args

            # Resolve alias to canonical task name
            try:
                dep_name = resolve_task_name(config, dep_name)
            except ValueError:
                raise UnknownTaskError(name, dep_name) from None

            add_task_recursive(dep_name, dep_args)
            graph.add_edge(name, dep_name)

    for task_name in task_names:
        add_task_recursive(task_name)

    return graph


def build_pipeline_graph(
    config: UvrConfig,
    pipeline_name: str,
) -> list[tuple[list[str], bool]]:
    """Build execution plan from a pipeline definition.

    Args:
        config: The pyr configuration.
        pipeline_name: Name of the pipeline.

    Returns:
        List of (task_names, parallel) tuples representing stages.
    """
    from uvtx.config import resolve_task_name

    pipeline = config.get_pipeline(pipeline_name)
    stages: list[tuple[list[str], bool]] = []

    for stage in pipeline.stages:
        # Resolve aliases to task names
        try:
            resolved_tasks = [resolve_task_name(config, task_name) for task_name in stage.tasks]
        except ValueError as e:
            msg = f"Pipeline '{pipeline_name}': {e}"
            raise KeyError(msg) from e
        stages.append((resolved_tasks, stage.parallel))

    return stages

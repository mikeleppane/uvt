"""Graph visualization formatters for task dependencies."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uvtx.graph import TaskGraph


def format_graph_ascii(graph: TaskGraph, root_task: str | None = None) -> str:
    """Format task dependency graph as ASCII tree.

    Args:
        graph: The task dependency graph
        root_task: Optional root task to start from (if None, shows all tasks)

    Returns:
        ASCII tree representation of the graph
    """
    output_lines: list[str] = []
    visited: set[str] = set()

    def render_tree(task: str, prefix: str = "", is_last: bool = True, path: set[str] | None = None) -> None:
        """Recursively render task tree with cycle detection."""
        if path is None:
            path = set()

        # Determine the connector
        connector = "└── " if is_last else "├── "

        # Check for circular dependency
        if task in path:
            output_lines.append(f"{prefix}{connector}{task} [CIRCULAR DEPENDENCY]")
            return

        # Check if already visited (but not in current path - allows shared dependencies)
        if task in visited:
            output_lines.append(f"{prefix}{connector}{task} [already shown above]")
            return

        # Add current task
        output_lines.append(f"{prefix}{connector}{task}")
        visited.add(task)

        # Get dependencies
        deps = sorted(graph.get_dependencies(task))

        if not deps:
            return

        # Prepare prefix for children
        extension = "    " if is_last else "│   "
        new_prefix = prefix + extension

        # Add current task to path for cycle detection
        new_path = path | {task}

        # Render each dependency
        for i, dep in enumerate(deps):
            is_last_dep = i == len(deps) - 1
            render_tree(dep, new_prefix, is_last_dep, new_path)

    if root_task:
        # Render single task tree
        output_lines.append(root_task)
        visited.add(root_task)
        deps = sorted(graph.get_dependencies(root_task))
        initial_path = {root_task}
        for i, dep in enumerate(deps):
            render_tree(dep, "", i == len(deps) - 1, initial_path)
    else:
        # Find root tasks (tasks with no incoming edges)
        all_deps: set[str] = set()
        for dep_set in graph.edges.values():
            all_deps.update(dep_set)

        roots = sorted(set(graph.nodes.keys()) - all_deps)

        if not roots:
            # No clear roots, show all tasks
            roots = sorted(graph.nodes.keys())

        for root in roots:
            output_lines.append(root)
            visited.add(root)
            deps = sorted(graph.get_dependencies(root))
            root_path = {root}
            for i, dep in enumerate(deps):
                render_tree(dep, "", i == len(deps) - 1, root_path)
            output_lines.append("")  # Blank line between trees

    return "\n".join(output_lines).rstrip()


def format_graph_dot(graph: TaskGraph, root_task: str | None = None) -> str:
    """Format task dependency graph as Graphviz DOT format.

    Args:
        graph: The task dependency graph
        root_task: Optional root task to filter to (if None, shows all tasks)

    Returns:
        DOT format string suitable for Graphviz
    """
    lines = ["digraph tasks {", "    rankdir=LR;  // Left to right layout", ""]

    # Determine which tasks to include
    if root_task:
        # Include root and all its dependencies
        tasks_to_include = {root_task} | graph.get_all_dependencies(root_task)
    else:
        tasks_to_include = set(graph.nodes.keys())

    # Add nodes with styling
    lines.extend(f'    "{task}";' for task in sorted(tasks_to_include))

    lines.append("")

    # Add edges
    for task in sorted(tasks_to_include):
        deps = graph.get_dependencies(task)
        lines.extend(f'    "{task}" -> "{dep}";' for dep in sorted(deps) if dep in tasks_to_include)

    lines.append("}")
    return "\n".join(lines)


def format_graph_mermaid(graph: TaskGraph, root_task: str | None = None) -> str:
    """Format task dependency graph as Mermaid diagram.

    Args:
        graph: The task dependency graph
        root_task: Optional root task to filter to (if None, shows all tasks)

    Returns:
        Mermaid diagram syntax
    """
    lines = ["graph TD"]

    # Determine which tasks to include
    if root_task:
        tasks_to_include = {root_task} | graph.get_all_dependencies(root_task)
    else:
        tasks_to_include = set(graph.nodes.keys())

    # Create node IDs (replace hyphens/special chars with underscores)
    def node_id(task: str) -> str:
        return task.replace("-", "_").replace(".", "_")

    # Add edges (Mermaid nodes are defined implicitly through edges)
    edges_added = False
    for task in sorted(tasks_to_include):
        deps = graph.get_dependencies(task)
        for dep in sorted(deps):
            if dep in tasks_to_include:
                lines.append(f"    {node_id(task)}[{task}] --> {node_id(dep)}[{dep}]")
                edges_added = True

    # If no edges, add standalone nodes
    if not edges_added:
        lines.extend(f"    {node_id(task)}[{task}]" for task in sorted(tasks_to_include))

    return "\n".join(lines)

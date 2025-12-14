"""Shell completion support for pt CLI."""

from __future__ import annotations

from typing import Any

from click.shell_completion import CompletionItem

from uvtx.config import ConfigNotFoundError, load_config


def complete_task_name(_ctx: Any, _param: Any, incomplete: str) -> list[CompletionItem]:
    """Complete task names from uvtx.toml.

    Args:
        _ctx: Click context (unused)
        _param: Click parameter (unused)
        incomplete: Incomplete string being completed

    Returns:
        List of completion items with task names and aliases
    """
    try:
        config, _ = load_config()
        tasks: list[CompletionItem] = []

        for name, task in config.tasks.items():
            # Skip private tasks (starting with _)
            if not name.startswith("_"):
                # Add main task name
                tasks.append(CompletionItem(name, help=task.description or ""))

                # Add aliases
                if task.aliases:
                    tasks.extend(
                        CompletionItem(alias, help=f"Alias for {name}") for alias in task.aliases
                    )

        return [t for t in tasks if t.value.startswith(incomplete)]
    except (ConfigNotFoundError, Exception):
        # Gracefully handle missing config or errors
        return []


def complete_profile_name(_ctx: Any, _param: Any, incomplete: str) -> list[CompletionItem]:
    """Complete profile names from uvtx.toml.

    Args:
        _ctx: Click context (unused)
        _param: Click parameter (unused)
        incomplete: Incomplete string being completed

    Returns:
        List of completion items with profile names
    """
    try:
        config, _ = load_config()
        profiles = [CompletionItem(name, help=f"Profile: {name}") for name in config.profiles]
        return [p for p in profiles if p.value.startswith(incomplete)]
    except (ConfigNotFoundError, Exception):
        return []


def complete_pipeline_name(_ctx: Any, _param: Any, incomplete: str) -> list[CompletionItem]:
    """Complete pipeline names from uvtx.toml.

    Args:
        _ctx: Click context (unused)
        _param: Click parameter (unused)
        incomplete: Incomplete string being completed

    Returns:
        List of completion items with pipeline names
    """
    try:
        config, _ = load_config()
        pipelines = [
            CompletionItem(name, help=pipe.description or "")
            for name, pipe in config.pipelines.items()
        ]
        return [p for p in pipelines if p.value.startswith(incomplete)]
    except (ConfigNotFoundError, Exception):
        return []

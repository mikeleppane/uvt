"""Variable interpolation and templating for pt configuration."""

from __future__ import annotations

import re
from typing import Any


class VariableInterpolationError(Exception):
    """Raised when variable interpolation fails."""


def interpolate_variables(
    value: str,
    variables: dict[str, str],
    context: str = "",
) -> str:
    """Interpolate variables in a string using Python format syntax.

    Supports:
    - {var_name} - Simple variable reference
    - Recursive variable expansion (variables can reference other variables)
    - Circular reference detection

    Args:
        value: String containing {var} placeholders
        variables: Dictionary of variable name -> value mappings
        context: Context string for error messages (e.g., "tasks.test.cmd")

    Returns:
        Interpolated string

    Raises:
        VariableInterpolationError: If variable not found or circular reference detected
    """
    # Track variables being resolved to detect circular references
    resolving: set[str] = set()

    def resolve_var(var_name: str) -> str:
        """Recursively resolve a variable value."""
        if var_name in resolving:
            chain = " -> ".join(resolving) + f" -> {var_name}"
            msg = f"Circular variable reference detected: {chain}"
            if context:
                msg = f"{context}: {msg}"
            raise VariableInterpolationError(msg)

        if var_name not in variables:
            msg = f"Variable '{var_name}' not found"
            if context:
                msg = f"{context}: {msg}"
            raise VariableInterpolationError(msg)

        resolving.add(var_name)
        var_value = variables[var_name]

        # Recursively interpolate the variable's value
        if "{" in var_value:
            var_value = interpolate_recursive(var_value)

        resolving.discard(var_name)
        return var_value

    def interpolate_recursive(text: str) -> str:
        """Recursively interpolate variables in text."""
        # Use Python's format() method for interpolation
        # Extract all {var_name} patterns
        pattern = re.compile(r"\{([a-zA-Z_][a-zA-Z0-9_]*)\}")

        def replacer(match: re.Match[str]) -> str:
            var_name = match.group(1)
            return resolve_var(var_name)

        return pattern.sub(replacer, text)

    return interpolate_recursive(value)


def interpolate_task_fields(
    task_dict: dict[str, Any],
    variables: dict[str, str],
    task_name: str,
) -> dict[str, Any]:
    """Interpolate variables in all relevant task fields.

    Fields to interpolate:
    - cmd
    - script
    - args (list elements)
    - env (values only, not keys)
    - cwd
    - dependencies (list elements)
    - before_task, after_task, after_success, after_failure

    Args:
        task_dict: Task configuration dictionary
        variables: Variables to interpolate
        task_name: Task name for error context

    Returns:
        New task dict with interpolated values
    """
    result = task_dict.copy()

    # String fields
    for field in [
        "cmd",
        "script",
        "cwd",
        "before_task",
        "after_task",
        "after_success",
        "after_failure",
    ]:
        if field in result and result[field] is not None:
            result[field] = interpolate_variables(
                result[field], variables, context=f"tasks.{task_name}.{field}"
            )

    # List fields (args, dependencies)
    for field in ["args", "dependencies"]:
        field_value = result.get(field)
        if field_value:
            result[field] = [
                interpolate_variables(item, variables, context=f"tasks.{task_name}.{field}")
                for item in field_value
            ]

    # Env dict (values only)
    env_value = result.get("env")
    if env_value:
        result["env"] = {
            key: interpolate_variables(val, variables, context=f"tasks.{task_name}.env.{key}")
            for key, val in env_value.items()
        }

    return result


def merge_variables(
    global_vars: dict[str, str],
    profile_vars: dict[str, str] | None = None,
) -> dict[str, str]:
    """Merge global and profile variables.

    Profile variables override global variables.

    Args:
        global_vars: Global variables from [variables]
        profile_vars: Profile-specific variables

    Returns:
        Merged variable dictionary
    """
    result = dict(global_vars)
    if profile_vars:
        result.update(profile_vars)
    return result

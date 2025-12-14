"""Parser for .env files."""

from __future__ import annotations

import os
import re
from pathlib import Path


def load_env_file(path: Path) -> dict[str, str]:
    """Parse a .env file and return a dictionary of environment variables.

    Supports:
    - KEY=value
    - KEY="value" (double-quoted, supports escape sequences)
    - KEY='value' (single-quoted, literal)
    - export KEY=value
    - Comments starting with #
    - Empty lines
    - Variable expansion: ${VAR} and $VAR

    Args:
        path: Path to the .env file.

    Returns:
        Dictionary mapping variable names to values.
    """
    if not path.exists():
        return {}

    result: dict[str, str] = {}
    content = path.read_text()

    for line in content.splitlines():
        line = line.strip()

        # Skip empty lines and comments
        if not line or line.startswith("#"):
            continue

        # Remove 'export ' prefix if present
        if line.startswith("export "):
            line = line[7:].strip()

        # Parse KEY=value
        match = re.match(r"^([A-Za-z_][A-Za-z0-9_]*)=(.*)$", line)
        if not match:
            continue

        key = match.group(1)
        value = match.group(2).strip()

        # Handle quoted values
        if value.startswith('"') and value.endswith('"') and len(value) >= 2:
            # Double-quoted: process escape sequences
            value = value[1:-1]
            value = _process_escape_sequences(value)
        elif value.startswith("'") and value.endswith("'") and len(value) >= 2:
            # Single-quoted: literal value
            value = value[1:-1]
        # Unquoted: strip inline comments
        elif " #" in value:
            value = value.split(" #")[0].strip()

        # Expand variables
        value = _expand_variables(value, result)

        result[key] = value

    return result


def _process_escape_sequences(value: str) -> str:
    """Process escape sequences in double-quoted strings."""
    replacements = [
        ("\\n", "\n"),
        ("\\t", "\t"),
        ("\\r", "\r"),
        ('\\"', '"'),
        ("\\\\", "\\"),
    ]
    for old, new in replacements:
        value = value.replace(old, new)
    return value


def _expand_variables(value: str, env: dict[str, str]) -> str:
    """Expand ${VAR} and $VAR references in a value.

    Args:
        value: The value containing variable references.
        env: Dictionary of already-parsed variables.

    Returns:
        Value with variables expanded.
    """

    # Expand ${VAR} syntax
    def replace_braced(match: re.Match[str]) -> str:
        var_name = match.group(1)
        # Check local env first, then system env
        return env.get(var_name, os.environ.get(var_name, ""))

    value = re.sub(r"\$\{([A-Za-z_][A-Za-z0-9_]*)\}", replace_braced, value)

    # Expand $VAR syntax (only if not followed by more word chars)
    def replace_simple(match: re.Match[str]) -> str:
        var_name = match.group(1)
        return env.get(var_name, os.environ.get(var_name, ""))

    value = re.sub(r"\$([A-Za-z_][A-Za-z0-9_]*)(?![A-Za-z0-9_])", replace_simple, value)

    return value


def load_env_files(files: list[str], project_root: Path) -> dict[str, str]:
    """Load multiple .env files in order, with later files overriding earlier ones.

    Args:
        files: List of .env file paths (relative to project_root or absolute).
        project_root: The project root directory.

    Returns:
        Merged dictionary of environment variables.
    """
    result: dict[str, str] = {}

    for file_path in files:
        path = Path(file_path)
        if not path.is_absolute():
            path = project_root / path

        file_env = load_env_file(path)
        result.update(file_env)

    return result

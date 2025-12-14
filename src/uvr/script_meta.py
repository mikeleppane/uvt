"""PEP 723 inline script metadata parser.

Parses inline metadata blocks from Python scripts in the format:

    # /// script
    # dependencies = ["requests", "rich"]
    # requires-python = ">=3.10"
    # ///

See: https://peps.python.org/pep-0723/
"""

from __future__ import annotations

import re
import sys
from dataclasses import dataclass, field
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


@dataclass
class ScriptMetadata:
    """Parsed metadata from a Python script."""

    dependencies: list[str] = field(default_factory=list)
    requires_python: str | None = None


# Pattern to match the entire script metadata block
_SCRIPT_BLOCK_PATTERN = re.compile(
    r"^# /// script\s*$\n"  # Opening marker
    r"((?:^#[^\n]*\n)*?)"  # Content lines (captured)
    r"^# ///\s*$",  # Closing marker
    re.MULTILINE,
)

# In-memory cache for parsed script metadata with mtime-based invalidation
# Key: script file path, Value: (mtime, parsed metadata)
_metadata_cache: dict[Path, tuple[float, ScriptMetadata]] = {}


def parse_script_metadata(script_path: Path) -> ScriptMetadata:
    """Parse PEP 723 inline metadata from a Python script with mtime-based caching.

    Args:
        script_path: Path to the Python script file.

    Returns:
        ScriptMetadata with parsed dependencies and python version.
        Returns empty metadata if no block found or parsing fails.
    """
    # Check cache with mtime validation
    current_mtime: float | None = None
    try:
        current_mtime = script_path.stat().st_mtime
        if script_path in _metadata_cache:
            cached_mtime, cached_metadata = _metadata_cache[script_path]
            if cached_mtime == current_mtime:
                # Cache hit - return cached metadata
                return cached_metadata
    except OSError:
        # If we can't stat the file, proceed without cache
        pass

    # Cache miss or invalidated - parse metadata
    try:
        content = script_path.read_text(encoding="utf-8")
    except OSError:
        return ScriptMetadata()

    metadata = parse_script_metadata_from_string(content)

    # Cache the result if we have mtime
    if current_mtime is not None:
        _metadata_cache[script_path] = (current_mtime, metadata)

    return metadata


def parse_script_metadata_from_string(content: str) -> ScriptMetadata:
    """Parse PEP 723 inline metadata from script content.

    Args:
        content: The script content as a string.

    Returns:
        ScriptMetadata with parsed dependencies and python version.
        Returns empty metadata if no block found or parsing fails.
    """
    match = _SCRIPT_BLOCK_PATTERN.search(content)
    if not match:
        return ScriptMetadata()

    # Extract the content between markers
    block_content = match.group(1)

    # Remove leading "# " from each line to get valid TOML
    lines: list[str] = []
    for line in block_content.split("\n"):
        if line.startswith("# "):
            lines.append(line[2:])
        elif line.startswith("#"):
            lines.append(line[1:])
        # Skip empty lines or lines that don't match the pattern

    toml_content = "\n".join(lines)

    try:
        data = tomllib.loads(toml_content)
    except tomllib.TOMLDecodeError:
        return ScriptMetadata()

    return ScriptMetadata(
        dependencies=data.get("dependencies", []),
        requires_python=data.get("requires-python"),
    )


def merge_dependencies(
    script_deps: list[str],
    config_deps: list[str],
) -> list[str]:
    """Merge script inline dependencies with config dependencies.

    Config dependencies take precedence (are added after script deps).
    Duplicates are removed while preserving order.

    Args:
        script_deps: Dependencies from PEP 723 inline metadata.
        config_deps: Dependencies from uvr.toml task config.

    Returns:
        Merged list of dependencies with duplicates removed.
    """
    seen: set[str] = set()
    result: list[str] = []

    # Script deps first, but config deps override (so add config deps last)
    for dep in script_deps + config_deps:
        # Normalize: extract package name without version specifier for dedup
        pkg_name = _extract_package_name(dep)
        if pkg_name not in seen:
            seen.add(pkg_name)
            result.append(dep)
        elif dep in config_deps:
            # Config version overrides script version
            result = [d for d in result if _extract_package_name(d) != pkg_name]
            result.append(dep)

    return result


def _extract_package_name(dep: str) -> str:
    """Extract the package name from a dependency specifier.

    Examples:
        "requests" -> "requests"
        "requests>=2.0" -> "requests"
        "requests[security]>=2.0" -> "requests"
    """
    # Remove extras like [security]
    name = re.split(r"[\[<>=!~]", dep, maxsplit=1)[0]
    return name.strip().lower()

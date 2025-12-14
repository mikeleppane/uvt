"""Configuration discovery and loading for pt."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from pydantic import ValidationError

from pt.models import PtConfig, TaskConfig

if sys.version_info >= (3, 11):
    import tomllib
else:
    import tomli as tomllib


class ConfigError(Exception):
    """Raised when configuration is invalid or cannot be loaded."""


class ConfigNotFoundError(ConfigError):
    """Raised when no configuration file is found."""


# In-memory cache for parsed configs with mtime-based invalidation
# Key: config file path, Value: (mtime, parsed config)
_config_cache: dict[Path, tuple[float, PtConfig]] = {}


def find_config_file(start_dir: Path | None = None) -> Path:
    """Find the pt config file by walking up the directory tree.

    Searches for:
    1. pt.toml (preferred)
    2. pyproject.toml with [tool.pt] section

    Args:
        start_dir: Directory to start searching from. Defaults to cwd.

    Returns:
        Path to the configuration file.

    Raises:
        ConfigNotFoundError: If no configuration file is found.
    """
    if start_dir is None:
        start_dir = Path.cwd()

    current = start_dir.resolve()

    while True:
        # Check for pt.toml first
        pt_toml = current / "pt.toml"
        if pt_toml.is_file():
            return pt_toml

        # Check for pyproject.toml with [tool.pt]
        pyproject = current / "pyproject.toml"
        if pyproject.is_file() and _has_pt_config(pyproject):
            return pyproject

        # Move up to parent
        parent = current.parent
        if parent == current:
            # Reached filesystem root
            break
        current = parent

    msg = (
        f"No pt configuration found. "
        f"Create a pt.toml or add [tool.pt] to pyproject.toml. "
        f"Searched from: {start_dir}"
    )
    raise ConfigNotFoundError(msg)


def _has_pt_config(pyproject_path: Path) -> bool:
    """Check if pyproject.toml contains [tool.pt] section.

    Fast path: Scan first ~100 lines for section headers before full TOML parse.
    This avoids parsing large pyproject.toml files (1000+ lines) just to check
    if [tool.pt] section exists.
    """
    try:
        # Fast path: scan for section headers without parsing
        with pyproject_path.open() as f:
            for i, line in enumerate(f):
                if i > 100:  # Only check first ~100 lines
                    break
                stripped = line.strip()
                # Check for [tool.pt] or [tool.pyr] (backward compat)
                if stripped in ("[tool.pt]", "[tool.pyr]"):
                    return True
                # Also check for subsections like [tool.pt.tasks]
                if stripped.startswith(("[tool.pt.", "[tool.pyr.")):
                    return True

        # Fallback: full TOML parse if section might be deeper in file
        # (rare but possible if file has many comments/blank lines at top)
        with pyproject_path.open("rb") as f:
            data = tomllib.load(f)
        return "tool" in data and ("pt" in data["tool"] or "pyr" in data["tool"])
    except (OSError, tomllib.TOMLDecodeError):
        return False


def load_config(config_path: Path | None = None) -> tuple[PtConfig, Path]:
    """Load and validate pt configuration with mtime-based caching.

    Args:
        config_path: Explicit path to config file. If None, will search.

    Returns:
        Tuple of (PtConfig, config_file_path).

    Raises:
        ConfigError: If config is invalid.
        ConfigNotFoundError: If no config file is found.
    """
    if config_path is None:
        config_path = find_config_file()

    # Check cache with mtime validation
    current_mtime: float | None = None
    try:
        current_mtime = config_path.stat().st_mtime
        if config_path in _config_cache:
            cached_mtime, cached_config = _config_cache[config_path]
            if cached_mtime == current_mtime:
                # Cache hit - return cached config
                return cached_config, config_path
    except OSError:
        # If we can't stat the file, proceed with normal load (will error below)
        pass

    # Cache miss or invalidated - load and parse config
    try:
        with config_path.open("rb") as f:
            raw_data = tomllib.load(f)
    except OSError as e:
        msg = f"Failed to read config file: {config_path}"
        raise ConfigError(msg) from e
    except tomllib.TOMLDecodeError as e:
        msg = f"Invalid TOML in config file: {config_path}\n{e}"
        raise ConfigError(msg) from e

    # Extract pyr config from pyproject.toml if needed
    if config_path.name == "pyproject.toml":
        pt_data = raw_data.get("tool", {}).get("pyr", {})
    else:
        pt_data = raw_data

    try:
        config = PtConfig.model_validate(pt_data)
    except ValidationError as e:
        msg = f"Invalid configuration in {config_path}:\n{_format_validation_errors(e)}"
        raise ConfigError(msg) from e

    # Resolve task inheritance
    config = resolve_task_inheritance(config)

    # Cache the resolved config with current mtime (if available)
    if current_mtime is not None:
        _config_cache[config_path] = (current_mtime, config)

    return config, config_path


def _format_validation_errors(error: ValidationError) -> str:
    """Format Pydantic validation errors for user-friendly display."""
    lines: list[str] = []
    for err in error.errors():
        loc = ".".join(str(part) for part in err["loc"])
        lines.append(f"  - {loc}: {err['msg']}")
    return "\n".join(lines)


def get_project_root(config_path: Path) -> Path:
    """Get the project root directory from config file path."""
    return config_path.parent


def resolve_task_inheritance(config: PtConfig) -> PtConfig:
    """Resolve task inheritance (extend field) for all tasks.

    Args:
        config: The configuration with unresolved task inheritance.

    Returns:
        Config with all task inheritance resolved.

    Raises:
        ConfigError: If circular inheritance is detected or parent task not found.
    """

    resolved: dict[str, TaskConfig] = {}
    resolving: set[str] = set()  # Track tasks being resolved to detect cycles

    def resolve_task(name: str) -> TaskConfig:
        """Recursively resolve a single task's inheritance."""
        if name in resolved:
            return resolved[name]

        if name not in config.tasks:
            msg = f"Task '{name}' not found (referenced in extend)"
            raise ConfigError(msg)

        task = config.tasks[name]

        # No inheritance - return as-is
        if task.extend is None:
            resolved[name] = task
            return task

        # Detect circular inheritance
        if name in resolving:
            msg = f"Circular task inheritance detected: {name}"
            raise ConfigError(msg)

        resolving.add(name)

        # Resolve parent first
        parent = resolve_task(task.extend)

        # Merge task with parent
        merged = _merge_task_configs(parent, task)
        resolved[name] = merged

        resolving.discard(name)
        return merged

    # Resolve all tasks
    for task_name in config.tasks:
        resolve_task(task_name)

    # Return new config with resolved tasks
    return config.model_copy(update={"tasks": resolved})


def _merge_task_configs(parent: TaskConfig, child: TaskConfig) -> TaskConfig:
    """Merge child task config with parent, following inheritance rules.

    Rules:
    - Override (child wins if set): script, cmd, cwd, timeout, python, description,
      condition, condition_script, ignore_errors, parallel
    - Merge lists (no duplicates): dependencies, pythonpath, depends_on
    - Merge args (parent + child)
    - Merge dicts (child overrides parent): env
    """
    from pt.models import TaskConfig

    # Start with parent values, override with child where child has values
    merged_data: dict[str, Any] = {}

    # Override fields - child wins if explicitly set (not default)
    override_fields = [
        "script",
        "cmd",
        "cwd",
        "timeout",
        "python",
        "description",
        "condition",
        "condition_script",
        "ignore_errors",
        "parallel",
        "before_task",
        "after_task",
        "after_success",
        "after_failure",
        "category",  # Category inherits from parent if not set in child
    ]
    for field in override_fields:
        child_val = getattr(child, field)
        parent_val = getattr(parent, field)
        # Use child value if it's set (not None/False/empty for these fields)
        if field in ("ignore_errors", "parallel"):
            # Booleans: child always wins
            merged_data[field] = child_val
        elif child_val is not None:
            merged_data[field] = child_val
        else:
            merged_data[field] = parent_val

    # Merge lists (unique values, parent first)
    for field in ("dependencies", "pythonpath"):
        parent_list = getattr(parent, field)
        child_list = getattr(child, field)
        merged = list(parent_list)
        seen = set(merged)  # O(1) lookup instead of O(n) list search
        for item in child_list:
            if item not in seen:
                merged.append(item)
                seen.add(item)
        merged_data[field] = merged

    # Merge depends_on (parent first, then child)
    parent_deps = parent.depends_on
    child_deps = child.depends_on
    merged_deps = list(parent_deps)
    for dep in child_deps:
        # Check if already present (compare task names)
        dep_name = dep if isinstance(dep, str) else dep.task
        existing_names = [d if isinstance(d, str) else d.task for d in merged_deps]
        if dep_name not in existing_names:
            merged_deps.append(dep)
    merged_data["depends_on"] = merged_deps

    # Merge args (parent args + child args)
    merged_data["args"] = list(parent.args) + list(child.args)

    # Merge env (child overrides parent)
    merged_env = dict(parent.env)
    merged_env.update(child.env)
    merged_data["env"] = merged_env

    # Keep child's aliases (don't inherit)
    merged_data["aliases"] = child.aliases

    # Merge tags (parent + child, deduplicated and sorted)
    merged_tags = list(set(parent.tags + child.tags))
    merged_data["tags"] = sorted(merged_tags)

    # Clear extend (inheritance is resolved)
    merged_data["extend"] = None

    return TaskConfig(**merged_data)


def resolve_path(path: str, project_root: Path) -> Path:
    """Resolve a relative path against the project root."""
    p = Path(path)
    if p.is_absolute():
        return p
    return (project_root / p).resolve()


def build_env(config: PtConfig, project_root: Path) -> dict[str, str]:
    """Build environment variables dict from config.

    Handles PYTHONPATH specially by joining list values with os.pathsep.
    """
    import os

    env: dict[str, str] = {}

    for key, value in config.env.items():
        if isinstance(value, list):
            # Join list values (like PYTHONPATH) with path separator
            resolved_paths = [str(resolve_path(p, project_root)) for p in value]
            env[key] = os.pathsep.join(resolved_paths)
        else:
            env[key] = value

    return env


def merge_env(
    *env_dicts: dict[str, str],
    pythonpath_lists: list[list[str]] | None = None,
    project_root: Path | None = None,
) -> dict[str, str]:
    """Merge multiple environment dictionaries.

    Later dicts override earlier ones. PYTHONPATH is handled specially
    by appending paths rather than replacing.
    """
    import os

    result: dict[str, str] = {}
    pythonpath_parts: list[str] = []

    for env in env_dicts:
        for key, value in env.items():
            if key == "PYTHONPATH" and value:
                pythonpath_parts.extend(value.split(os.pathsep))
            else:
                result[key] = value

    # Add additional PYTHONPATH entries
    if pythonpath_lists and project_root:
        seen_paths = set(pythonpath_parts)  # O(1) lookup instead of O(n) list search
        for paths in pythonpath_lists:
            for p in paths:
                resolved = str(resolve_path(p, project_root))
                if resolved not in seen_paths:
                    pythonpath_parts.append(resolved)
                    seen_paths.add(resolved)

    if pythonpath_parts:
        result["PYTHONPATH"] = os.pathsep.join(pythonpath_parts)

    return result


def get_effective_profile(
    config: PtConfig,
    profile_name: str | None = None,
) -> str | None:
    """Determine the effective profile to use.

    Priority:
    1. Explicitly passed profile_name
    2. PT_PROFILE environment variable
    3. config.project.default_profile

    Args:
        config: The pyr configuration.
        profile_name: Explicitly requested profile name.

    Returns:
        The profile name to use, or None if no profile.
    """
    import os

    if profile_name:
        return profile_name

    env_profile = os.environ.get("PT_PROFILE")
    if env_profile:
        return env_profile

    return config.project.default_profile


def build_profile_env(
    config: PtConfig,
    project_root: Path,
    profile_name: str | None = None,
) -> dict[str, str]:
    """Build environment variables with profile and .env file support.

    Loads environment from:
    1. Global .env files (config.env_files)
    2. Global env vars (config.env)
    3. Profile .env files
    4. Profile env vars

    Args:
        config: The pyr configuration.
        project_root: The project root directory.
        profile_name: Profile to apply (uses get_effective_profile if None).

    Returns:
        Merged environment dictionary.
    """
    from pt.dotenv import load_env_files

    result: dict[str, str] = {}

    # 1. Load global .env files
    if config.env_files:
        env_from_files = load_env_files(config.env_files, project_root)
        result.update(env_from_files)

    # 2. Apply global env vars from config
    global_env = build_env(config, project_root)
    result.update(global_env)

    # 3. Get effective profile
    effective_profile = get_effective_profile(config, profile_name)
    profile = config.get_profile(effective_profile)

    if profile:
        # 4. Load profile .env files
        if profile.env_files:
            profile_env_files = load_env_files(profile.env_files, project_root)
            result.update(profile_env_files)

        # 5. Apply profile env vars
        result.update(profile.env)

    return result


def get_profile_python(
    config: PtConfig,
    profile_name: str | None = None,
) -> str | None:
    """Get the Python version to use, considering profile override.

    Args:
        config: The pyr configuration.
        profile_name: Profile to check for override.

    Returns:
        Python version string or None.
    """
    effective_profile = get_effective_profile(config, profile_name)
    profile = config.get_profile(effective_profile)

    if profile and profile.python:
        return profile.python

    return config.project.python


def get_profile_dependencies(
    config: PtConfig,
    profile_name: str | None = None,
) -> dict[str, list[str]]:
    """Get dependency groups, with profile overrides applied.

    Args:
        config: The pyr configuration.
        profile_name: Profile to check for overrides.

    Returns:
        Merged dependency groups dictionary.
    """
    result = dict(config.dependencies)

    effective_profile = get_effective_profile(config, profile_name)
    profile = config.get_profile(effective_profile)

    if profile:
        # Profile dependencies override global ones
        result.update(profile.dependencies)

    return result


def resolve_task_name(config: PtConfig, name_or_alias: str) -> str:
    """Resolve task alias to canonical task name.

    Args:
        config: The pt configuration
        name_or_alias: Task name or alias

    Returns:
        Canonical task name

    Raises:
        ValueError: If name_or_alias doesn't match any task or alias
    """
    # Check if it's a task name
    if name_or_alias in config.tasks:
        return name_or_alias

    # Check if it's an alias
    for task_name, task in config.tasks.items():
        if name_or_alias in task.aliases:
            return task_name

    # Not found - generate helpful error message
    from difflib import get_close_matches

    all_names = list(config.tasks.keys())
    all_aliases = [alias for task in config.tasks.values() for alias in task.aliases]
    suggestions = get_close_matches(name_or_alias, all_names + all_aliases, n=3, cutoff=0.6)

    msg = f"Task or alias '{name_or_alias}' not found"
    if suggestions:
        msg += f". Did you mean: {', '.join(suggestions)}?"
    raise ValueError(msg)

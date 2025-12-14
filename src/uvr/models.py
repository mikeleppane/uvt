"""Pydantic models for pt configuration schema."""

from __future__ import annotations

from difflib import get_close_matches
from enum import Enum
from typing import Annotated, Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class OnFailure(str, Enum):
    """Behavior when a task fails in parallel execution."""

    FAIL_FAST = "fail-fast"  # Stop all running tasks immediately
    WAIT = "wait"  # Let running tasks complete, don't start new ones
    CONTINUE = "continue"  # Continue all tasks, report failures at end


class OutputMode(str, Enum):
    """How to display output from parallel tasks."""

    INTERLEAVED = "interleaved"  # Real-time output from all tasks
    BUFFERED = "buffered"  # Show each task's output after completion


class TaskDependency(BaseModel):
    """A task dependency with optional argument overrides."""

    model_config = ConfigDict(extra="forbid")

    task: str
    args: list[str] = Field(default_factory=list)


class ConditionConfig(BaseModel):
    """Conditions for task execution."""

    model_config = ConfigDict(extra="forbid")

    # Platform conditions
    platforms: list[str] = Field(default_factory=list)  # ["linux", "macos", "windows"]

    # Python version condition
    python_version: str | None = None  # e.g., ">=3.10", "==3.11"

    # Environment variable conditions
    env_set: list[str] = Field(default_factory=list)  # Env vars that must be set
    env_not_set: list[str] = Field(default_factory=list)  # Env vars that must NOT be set
    env_true: list[str] = Field(default_factory=list)  # Env vars that must be truthy
    env_false: list[str] = Field(default_factory=list)  # Env vars that must be falsy
    env_equals: dict[str, str] = Field(default_factory=dict)  # Env var == value
    env_contains: dict[str, str] = Field(default_factory=dict)  # Env var contains value

    # File conditions
    files_exist: list[str] = Field(default_factory=list)  # Files that must exist
    files_not_exist: list[str] = Field(default_factory=list)  # Files that must NOT exist


class TaskConfig(BaseModel):
    """Configuration for a single task."""

    model_config = ConfigDict(extra="forbid")

    description: str = ""
    script: str | None = None
    cmd: str | None = None
    args: list[str] = Field(default_factory=list)
    dependencies: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    pythonpath: list[str] = Field(default_factory=list)
    depends_on: list[str | TaskDependency] = Field(default_factory=list)
    parallel: bool = False
    python: str | None = None

    # Execution options
    cwd: str | None = None  # Working directory for task execution
    ignore_errors: bool = False  # Continue even if task fails
    timeout: int | None = None  # Timeout in seconds
    condition: ConditionConfig | None = None  # Conditional execution
    condition_script: str | None = None  # Script that must exit 0 for task to run

    # Task organization
    aliases: list[str] = Field(default_factory=list)  # Alternative names for this task
    extend: str | None = None  # Inherit from another task
    tags: list[str] = Field(default_factory=list)  # Tags for organizing and filtering tasks
    category: str | None = None  # Category for logical grouping (testing, build, deploy, etc.)

    # Task hooks
    before_task: str | None = None  # Script/command to run before task
    after_task: str | None = None  # Script/command to run after task (always)
    after_success: str | None = None  # Script/command to run after successful task
    after_failure: str | None = None  # Script/command to run after failed task

    # Variable interpolation
    use_vars: bool | None = (
        None  # Per-task opt-in for variable interpolation (None = use global default)
    )

    # Runner prefix
    disable_runner: bool = False  # Opt-out of global runner for this task

    # Output redirection
    stdout: str | None = None  # "null", "inherit", or file path for stdout
    stderr: str | None = None  # "null", "inherit", or file path for stderr

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, v: list[str]) -> list[str]:
        """Validate tag names."""
        for tag in v:
            if not tag:
                msg = "Tag cannot be empty"
                raise ValueError(msg)
            # Allow alphanumeric, hyphens, and underscores
            if not tag.replace("-", "").replace("_", "").isalnum():
                msg = f"Tag '{tag}' must be alphanumeric (hyphens and underscores allowed)"
                raise ValueError(msg)
        return v

    @model_validator(mode="after")
    def validate_script_or_cmd(self) -> TaskConfig:
        """Ensure either script or cmd is set, but not both (unless depends_on only)."""
        has_execution = self.script is not None or self.cmd is not None
        has_depends_on = len(self.depends_on) > 0
        has_extend = self.extend is not None

        # If task uses extend, it will inherit script/cmd from parent after resolution
        if not has_execution and not has_depends_on and not has_extend:
            msg = "Task must have either 'script', 'cmd', or 'depends_on'"
            raise ValueError(msg)

        if self.script is not None and self.cmd is not None:
            msg = "Task cannot have both 'script' and 'cmd'"
            raise ValueError(msg)

        # Validate output redirection
        for field_name in ("stdout", "stderr"):
            value = getattr(self, field_name)
            # It's a file path - validate it's not empty
            if value is not None and value not in ("null", "inherit") and not value.strip():
                msg = f"{field_name} file path cannot be empty"
                raise ValueError(msg)

        return self


class StageConfig(BaseModel):
    """A stage in a pipeline with tasks to run."""

    model_config = ConfigDict(extra="forbid")

    tasks: list[str]
    parallel: bool = False


class PipelineConfig(BaseModel):
    """Configuration for a multi-stage pipeline."""

    model_config = ConfigDict(extra="forbid")

    description: str = ""
    stages: list[StageConfig]
    on_failure: OnFailure = OnFailure.FAIL_FAST
    output: OutputMode = OutputMode.BUFFERED


class ProfileConfig(BaseModel):
    """Configuration for a profile (dev, ci, prod, etc.)."""

    model_config = ConfigDict(extra="forbid")

    env: dict[str, str] = Field(default_factory=dict)  # Additional env vars
    dependencies: dict[str, list[str]] = Field(default_factory=dict)  # Override dependency groups
    python: str | None = None  # Override Python version
    env_files: list[str] = Field(default_factory=list)  # .env files for this profile
    variables: dict[str, str] = Field(default_factory=dict)  # Profile-specific variable overrides
    runner: str | None = None  # Profile-specific runner override


class ProjectConfig(BaseModel):
    """Project-level configuration."""

    model_config = ConfigDict(extra="forbid")

    name: str = ""
    python: str | None = None
    default_profile: str | None = None  # Default profile to use
    on_error_task: str | None = None  # Task to run when any task fails
    use_vars: bool = False  # Global default for variable interpolation
    runner: str | None = None  # Global command prefix for all tasks


class UvrConfig(BaseModel):
    """Root configuration model for uvr.toml."""

    model_config = ConfigDict(extra="forbid")

    project: ProjectConfig = Field(default_factory=ProjectConfig)
    variables: dict[str, str] = Field(default_factory=dict)  # Global variables for templating
    env: dict[str, Annotated[str | list[str], Field()]] = Field(default_factory=dict)
    env_files: list[str] = Field(default_factory=list)  # Global .env files to load
    dependencies: dict[str, list[str]] = Field(default_factory=dict)
    tasks: dict[str, TaskConfig] = Field(default_factory=dict)
    pipelines: dict[str, PipelineConfig] = Field(default_factory=dict)
    profiles: dict[str, ProfileConfig] = Field(default_factory=dict)

    @field_validator("env", mode="before")
    @classmethod
    def normalize_env_values(cls, v: dict[str, Any]) -> dict[str, str | list[str]]:
        """Ensure env values are either strings or lists of strings."""
        result: dict[str, str | list[str]] = {}
        for key, value in v.items():
            if isinstance(value, list):
                result[key] = [str(item) for item in value]
            else:
                result[key] = str(value)
        return result

    @model_validator(mode="after")
    def validate_config(self) -> UvrConfig:
        """Validate aliases are unique."""
        return self.validate_aliases()

    def get_task(self, name: str) -> TaskConfig:
        """Get a task by name or alias, raising KeyError if not found."""
        # Direct lookup first
        if name in self.tasks:
            return self.tasks[name]

        # Alias lookup
        for task in self.tasks.values():
            if name in task.aliases:
                return task

        # Task not found - provide helpful error with suggestions
        suggestions = get_close_matches(name, self.tasks.keys(), n=3, cutoff=0.6)
        msg = f"Task '{name}' not found."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        else:
            msg += f" Available tasks: {', '.join(sorted(self.tasks.keys()))}"
        raise KeyError(msg)

    def get_task_name(self, name: str) -> str:
        """Get the canonical task name (resolves aliases to actual task names)."""
        # Direct lookup first
        if name in self.tasks:
            return name

        # Alias lookup
        for task_name, task in self.tasks.items():
            if name in task.aliases:
                return task_name

        # Task not found - provide helpful error with suggestions
        suggestions = get_close_matches(name, self.tasks.keys(), n=3, cutoff=0.6)
        msg = f"Task '{name}' not found."
        if suggestions:
            msg += f" Did you mean: {', '.join(suggestions)}?"
        else:
            msg += f" Available tasks: {', '.join(sorted(self.tasks.keys()))}"
        raise KeyError(msg)

    def get_pipeline(self, name: str) -> PipelineConfig:
        """Get a pipeline by name, raising KeyError if not found."""
        if name not in self.pipelines:
            suggestions = get_close_matches(name, self.pipelines.keys(), n=3, cutoff=0.6)
            msg = f"Pipeline '{name}' not found."
            if suggestions:
                msg += f" Did you mean: {', '.join(suggestions)}?"
            else:
                msg += f" Available pipelines: {', '.join(sorted(self.pipelines.keys()))}"
            raise KeyError(msg)
        return self.pipelines[name]

    def get_profile(self, name: str | None) -> ProfileConfig | None:
        """Get a profile by name, or None if not found or name is None."""
        if name is None:
            return None
        return self.profiles.get(name)

    def resolve_dependencies(self, task: TaskConfig) -> list[str]:
        """Resolve dependency group references to actual package names."""
        resolved: list[str] = []
        for dep in task.dependencies:
            if dep in self.dependencies:
                resolved.extend(self.dependencies[dep])
            else:
                resolved.append(dep)
        return resolved

    def get_tasks_by_tag(self, tag: str) -> dict[str, TaskConfig]:
        """Get all tasks with a specific tag.

        Args:
            tag: Tag to filter by

        Returns:
            Dictionary of task name to TaskConfig for tasks with the specified tag
        """
        return {name: task for name, task in self.tasks.items() if tag in task.tags}

    def get_tasks_by_tags(self, tags: list[str], match_all: bool = True) -> dict[str, TaskConfig]:
        """Get tasks matching tags.

        Args:
            tags: List of tags to match
            match_all: If True, task must have ALL tags. If False, ANY tag.

        Returns:
            Dictionary of task name to TaskConfig for matching tasks
        """
        if match_all:
            return {
                name: task
                for name, task in self.tasks.items()
                if all(tag in task.tags for tag in tags)
            }
        else:
            return {
                name: task
                for name, task in self.tasks.items()
                if any(tag in task.tags for tag in tags)
            }

    def get_all_tags(self) -> set[str]:
        """Get all unique tags across all tasks.

        Returns:
            Set of all tag strings used in any task
        """
        all_tags: set[str] = set()
        for task in self.tasks.values():
            all_tags.update(task.tags)
        return all_tags

    def get_tasks_by_category(self, category: str) -> dict[str, TaskConfig]:
        """Get all tasks with a specific category.

        Args:
            category: Category to filter by

        Returns:
            Dictionary of task name to TaskConfig for tasks with the specified category
        """
        return {name: task for name, task in self.tasks.items() if task.category == category}

    def get_all_categories(self) -> dict[str, int]:
        """Get all categories with task counts.

        Returns:
            Dictionary mapping category name to count of tasks in that category
        """
        categories: dict[str, int] = {}
        for task in self.tasks.values():
            if task.category:
                categories[task.category] = categories.get(task.category, 0) + 1
        return categories

    def validate_aliases(self) -> UvrConfig:
        """Ensure aliases are globally unique across all tasks.

        Returns:
            Self for method chaining

        Raises:
            ValueError: If duplicate aliases or alias conflicts with task name
        """
        alias_to_task: dict[str, str] = {}

        for task_name, task in self.tasks.items():
            for alias in task.aliases:
                if alias in alias_to_task:
                    msg = (
                        f"Duplicate alias '{alias}' found in tasks "
                        f"'{task_name}' and '{alias_to_task[alias]}'"
                    )
                    raise ValueError(msg)
                if alias in self.tasks:
                    msg = f"Alias '{alias}' conflicts with task name in task '{task_name}'"
                    raise ValueError(msg)
                alias_to_task[alias] = task_name

        return self

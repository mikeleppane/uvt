"""Condition evaluation service for task execution."""

from __future__ import annotations

import os
import platform
import re
import sys
from pathlib import Path
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from uvr.models import ConditionConfig


class ConditionEvaluator:
    """Evaluates task execution conditions.

    Separates condition evaluation logic from the ConditionConfig model,
    removing side effects (file I/O, environment checks) from the data model.
    """

    def __init__(self, project_root: Path | None = None):
        """Initialize condition evaluator.

        Args:
            project_root: Project root directory for resolving file paths.
                         Defaults to current working directory.
        """
        self.project_root = project_root or Path.cwd()

    def evaluate(self, condition: ConditionConfig) -> tuple[bool, str]:
        """Evaluate all conditions.

        Args:
            condition: Condition configuration to evaluate.

        Returns:
            Tuple of (passed, reason). If passed is False, reason explains why.
        """
        # Platform check
        if condition.platforms:
            current_platform = self._get_current_platform()
            if current_platform not in condition.platforms:
                return False, f"Platform '{current_platform}' not in {condition.platforms}"

        # Python version check
        if condition.python_version and not self._check_python_version(condition.python_version):
            current = f"{sys.version_info.major}.{sys.version_info.minor}"
            return False, f"Python {current} does not satisfy {condition.python_version}"

        # Environment variable checks
        for var in condition.env_set:
            if var not in os.environ:
                return False, f"Environment variable '{var}' is not set"

        for var in condition.env_not_set:
            if var in os.environ:
                return False, f"Environment variable '{var}' should not be set"

        for var in condition.env_true:
            value = os.environ.get(var, "").lower()
            if value not in ("1", "true", "yes", "on"):
                return False, f"Environment variable '{var}' is not truthy"

        for var in condition.env_false:
            value = os.environ.get(var, "").lower()
            if value in ("1", "true", "yes", "on"):
                return False, f"Environment variable '{var}' is not falsy"

        for var, expected in condition.env_equals.items():
            actual = os.environ.get(var, "")
            if actual != expected:
                return False, f"Environment variable '{var}' is '{actual}', expected '{expected}'"

        for var, substring in condition.env_contains.items():
            actual = os.environ.get(var, "")
            if substring not in actual:
                return False, f"Environment variable '{var}' does not contain '{substring}'"

        # File existence checks
        for file_path in condition.files_exist:
            full_path = (
                self.project_root / file_path
                if not Path(file_path).is_absolute()
                else Path(file_path)
            )
            if not full_path.exists():
                return False, f"Required file does not exist: {file_path}"

        for file_path in condition.files_not_exist:
            full_path = (
                self.project_root / file_path
                if not Path(file_path).is_absolute()
                else Path(file_path)
            )
            if full_path.exists():
                return False, f"File should not exist: {file_path}"

        return True, ""

    @staticmethod
    def _get_current_platform() -> str:
        """Get normalized current platform name."""
        system = platform.system().lower()
        if system == "darwin":
            return "macos"
        return system  # "linux", "windows"

    @staticmethod
    def _check_python_version(spec: str) -> bool:
        """Check if current Python version satisfies the specifier."""
        current = (sys.version_info.major, sys.version_info.minor, sys.version_info.micro)

        # Parse simple specifiers like ">=3.10", "==3.11", "<3.12"
        match = re.match(r"(>=|<=|==|!=|>|<)?\s*(\d+)\.(\d+)(?:\.(\d+))?", spec)
        if not match:
            return True  # Invalid spec, assume OK

        op = match.group(1) or ">="
        major = int(match.group(2))
        minor = int(match.group(3))
        micro = int(match.group(4)) if match.group(4) else 0
        required = (major, minor, micro)

        ops = {
            ">=": current >= required,
            "<=": current <= required,
            "==": current[:2] == required[:2],  # Only compare major.minor for ==
            "!=": current[:2] != required[:2],
            ">": current > required,
            "<": current < required,
        }
        return ops.get(op, True)

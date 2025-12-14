"""Tests for built-in environment variables."""

import os
import textwrap
from pathlib import Path

from uvr.config import load_config
from uvr.runner import Runner, _detect_ci_environment, _get_git_info


def test_builtin_env_essential_variables(tmp_path: Path) -> None:
    """Test that essential built-in env vars are set."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert builtin_env["UVR_TASK_NAME"] == "test"
    assert builtin_env["UVR_PROJECT_ROOT"] == str(tmp_path)
    assert builtin_env["UVR_CONFIG_FILE"] == str(config_file)


def test_builtin_env_with_profile(tmp_path: Path) -> None:
    """Test that UVR_PROFILE is set when using a profile."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"

            [profiles.dev]
            env = { DEBUG = "true" }
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file, profile="dev")

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert builtin_env["UVR_PROFILE"] == "dev"


def test_builtin_env_without_profile(tmp_path: Path) -> None:
    """Test that UVR_PROFILE is not set when not using a profile."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert "UVR_PROFILE" not in builtin_env


def test_builtin_env_with_python_version(tmp_path: Path) -> None:
    """Test that UVR_PYTHON_VERSION is set from project config."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"
            python = "3.11"

            [tasks.test]
            cmd = "echo test"
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert builtin_env["UVR_PYTHON_VERSION"] == "3.11"


def test_builtin_env_with_task_python_version(tmp_path: Path) -> None:
    """Test that task-level python version overrides project level."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"
            python = "3.10"

            [tasks.test]
            cmd = "echo test"
            python = "3.12"
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert builtin_env["UVR_PYTHON_VERSION"] == "3.12"


def test_builtin_env_with_tags(tmp_path: Path) -> None:
    """Test that UVR_TAGS is set and sorted."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
            tags = ["ci", "unit", "fast"]
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert builtin_env["UVR_TAGS"] == "ci,fast,unit"  # Alphabetically sorted


def test_builtin_env_without_tags(tmp_path: Path) -> None:
    """Test that UVR_TAGS is not set when task has no tags."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    builtin_env = runner._build_builtin_env("test", config.tasks["test"])

    assert "UVR_TAGS" not in builtin_env


def test_detect_ci_environment_github_actions() -> None:
    """Test CI detection for GitHub Actions."""
    original = os.environ.get("GITHUB_ACTIONS")
    try:
        os.environ["GITHUB_ACTIONS"] = "true"
        assert _detect_ci_environment() is True
    finally:
        if original:
            os.environ["GITHUB_ACTIONS"] = original
        else:
            os.environ.pop("GITHUB_ACTIONS", None)


def test_detect_ci_environment_gitlab_ci() -> None:
    """Test CI detection for GitLab CI."""
    original = os.environ.get("GITLAB_CI")
    try:
        os.environ["GITLAB_CI"] = "true"
        assert _detect_ci_environment() is True
    finally:
        if original:
            os.environ["GITLAB_CI"] = original
        else:
            os.environ.pop("GITLAB_CI", None)


def test_detect_ci_environment_generic() -> None:
    """Test CI detection for generic CI variable."""
    original = os.environ.get("CI")
    try:
        os.environ["CI"] = "true"
        assert _detect_ci_environment() is True
    finally:
        if original:
            os.environ["CI"] = original
        else:
            os.environ.pop("CI", None)


def test_detect_ci_environment_not_ci() -> None:
    """Test CI detection when not in CI."""
    # Save all CI vars
    ci_vars = [
        "CI",
        "CONTINUOUS_INTEGRATION",
        "GITHUB_ACTIONS",
        "GITLAB_CI",
        "CIRCLECI",
        "TRAVIS",
        "JENKINS_HOME",
        "BUILDKITE",
    ]
    saved = {var: os.environ.get(var) for var in ci_vars}

    try:
        # Clear all CI vars
        for var in ci_vars:
            os.environ.pop(var, None)

        assert _detect_ci_environment() is False
    finally:
        # Restore
        for var, value in saved.items():
            if value:
                os.environ[var] = value


def test_get_git_info_returns_tuple() -> None:
    """Test that _get_git_info returns a tuple."""
    branch, commit = _get_git_info()
    assert isinstance(branch, (str, type(None)))
    assert isinstance(commit, (str, type(None)))


def test_builtin_env_integrated_into_task(tmp_path: Path) -> None:
    """Test that builtin env vars are included in task command."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"
            python = "3.11"

            [tasks.test]
            cmd = "echo test"
            tags = ["ci"]
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    cmd = runner.build_command(config.tasks["test"], "test")

    # Check that builtin env vars are in the final command env
    assert cmd.env["UVR_TASK_NAME"] == "test"
    assert cmd.env["UVR_PROJECT_ROOT"] == str(tmp_path)
    assert cmd.env["UVR_CONFIG_FILE"] == str(config_file)
    assert cmd.env["UVR_PYTHON_VERSION"] == "3.11"
    assert cmd.env["UVR_TAGS"] == "ci"


def test_builtin_env_does_not_override_user_env(tmp_path: Path) -> None:
    """Test that user-defined env vars can override builtin vars."""
    config_file = tmp_path / "uvr.toml"
    config_file.write_text(
        textwrap.dedent("""
            [project]
            name = "test"

            [tasks.test]
            cmd = "echo test"
            env = { UVR_TASK_NAME = "custom" }
        """)
    )

    config, _ = load_config(config_file)
    runner = Runner(config=config, project_root=tmp_path, config_path=config_file)

    cmd = runner.build_command(config.tasks["test"], "test")

    # Task env should override builtin
    assert cmd.env["UVR_TASK_NAME"] == "custom"

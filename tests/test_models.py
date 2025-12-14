"""Tests for pt.models."""

import pytest
from pydantic import ValidationError

from pt.models import (
    OnFailure,
    OutputMode,
    PipelineConfig,
    PtConfig,
    StageConfig,
    TaskConfig,
    TaskDependency,
)


class TestTaskConfig:
    """Tests for TaskConfig model."""

    def test_valid_script_task(self) -> None:
        task = TaskConfig(script="scripts/run.py")
        assert task.script == "scripts/run.py"
        assert task.cmd is None

    def test_valid_cmd_task(self) -> None:
        task = TaskConfig(cmd="python -c 'print(1)'")
        assert task.cmd == "python -c 'print(1)'"
        assert task.script is None

    def test_valid_depends_on_only(self) -> None:
        task = TaskConfig(depends_on=["lint", "test"])
        assert task.depends_on == ["lint", "test"]
        assert task.script is None
        assert task.cmd is None

    def test_invalid_both_script_and_cmd(self) -> None:
        with pytest.raises(ValidationError, match="cannot have both"):
            TaskConfig(script="run.py", cmd="python run.py")

    def test_invalid_empty_task(self) -> None:
        with pytest.raises(ValidationError, match="must have either"):
            TaskConfig()

    def test_task_with_dependencies(self) -> None:
        task = TaskConfig(
            script="run.py",
            dependencies=["pytest", "requests"],
            env={"DEBUG": "1"},
            pythonpath=["src"],
        )
        assert task.dependencies == ["pytest", "requests"]
        assert task.env == {"DEBUG": "1"}
        assert task.pythonpath == ["src"]

    def test_task_with_task_dependency_objects(self) -> None:
        task = TaskConfig(
            depends_on=[
                "simple_task",
                TaskDependency(task="complex_task", args=["--verbose"]),
            ]
        )
        assert len(task.depends_on) == 2
        assert task.depends_on[0] == "simple_task"
        assert isinstance(task.depends_on[1], TaskDependency)
        assert task.depends_on[1].task == "complex_task"


class TestPipelineConfig:
    """Tests for PipelineConfig model."""

    def test_valid_pipeline(self) -> None:
        pipeline = PipelineConfig(
            stages=[
                StageConfig(tasks=["lint", "typecheck"], parallel=True),
                StageConfig(tasks=["test"]),
            ]
        )
        assert len(pipeline.stages) == 2
        assert pipeline.stages[0].parallel is True
        assert pipeline.stages[1].parallel is False

    def test_pipeline_with_options(self) -> None:
        pipeline = PipelineConfig(
            description="CI pipeline",
            stages=[StageConfig(tasks=["test"])],
            on_failure=OnFailure.CONTINUE,
            output=OutputMode.INTERLEAVED,
        )
        assert pipeline.on_failure == OnFailure.CONTINUE
        assert pipeline.output == OutputMode.INTERLEAVED


class TestPtConfig:
    """Tests for PtConfig model."""

    def test_empty_config(self) -> None:
        config = PtConfig()
        assert config.tasks == {}
        assert config.pipelines == {}
        assert config.dependencies == {}

    def test_full_config(self) -> None:
        config = PtConfig(
            env={"PYTHONPATH": ["src"], "DEBUG": "1"},
            dependencies={
                "common": ["requests"],
                "testing": ["pytest"],
            },
            tasks={
                "test": TaskConfig(cmd="pytest", dependencies=["testing"]),
            },
        )
        assert config.env["DEBUG"] == "1"
        assert config.dependencies["common"] == ["requests"]
        assert "test" in config.tasks

    def test_get_task(self) -> None:
        config = PtConfig(tasks={"test": TaskConfig(cmd="pytest")})
        task = config.get_task("test")
        assert task.cmd == "pytest"

    def test_get_task_not_found(self) -> None:
        config = PtConfig()
        with pytest.raises(KeyError, match="not found"):
            config.get_task("nonexistent")

    def test_resolve_dependencies_group(self) -> None:
        config = PtConfig(
            dependencies={"testing": ["pytest", "pytest-cov"]},
            tasks={"test": TaskConfig(cmd="pytest", dependencies=["testing"])},
        )
        resolved = config.resolve_dependencies(config.tasks["test"])
        assert resolved == ["pytest", "pytest-cov"]

    def test_resolve_dependencies_mixed(self) -> None:
        config = PtConfig(
            dependencies={"testing": ["pytest"]},
            tasks={
                "test": TaskConfig(
                    cmd="pytest",
                    dependencies=["testing", "requests"],
                )
            },
        )
        resolved = config.resolve_dependencies(config.tasks["test"])
        assert resolved == ["pytest", "requests"]

    def test_env_list_values(self) -> None:
        config = PtConfig(env={"PYTHONPATH": ["src", "lib"]})
        assert config.env["PYTHONPATH"] == ["src", "lib"]

    def test_env_string_values(self) -> None:
        config = PtConfig(env={"DEBUG": "1"})
        assert config.env["DEBUG"] == "1"


class TestEnums:
    """Tests for enum values."""

    def test_on_failure_values(self) -> None:
        assert OnFailure.FAIL_FAST.value == "fail-fast"
        assert OnFailure.WAIT.value == "wait"
        assert OnFailure.CONTINUE.value == "continue"

    def test_output_mode_values(self) -> None:
        assert OutputMode.INTERLEAVED.value == "interleaved"
        assert OutputMode.BUFFERED.value == "buffered"

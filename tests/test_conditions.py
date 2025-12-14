"""Tests for pt.condition_evaluator.ConditionEvaluator."""

import os
import platform
import sys
from pathlib import Path

from uvr.condition_evaluator import ConditionEvaluator
from uvr.models import ConditionConfig


class TestPlatformCondition:
    """Tests for platform-based conditions."""

    def test_current_platform_passes(self) -> None:
        current = "macos" if platform.system() == "Darwin" else platform.system().lower()
        condition = ConditionConfig(platforms=[current])
        evaluator = ConditionEvaluator()
        passed, reason = evaluator.evaluate(condition)
        assert passed
        assert reason == ""

    def test_other_platform_fails(self) -> None:
        # Use a platform that's definitely not the current one
        other_platforms = {"linux", "macos", "windows"} - {
            "macos" if platform.system() == "Darwin" else platform.system().lower()
        }
        condition = ConditionConfig(platforms=list(other_platforms))
        evaluator = ConditionEvaluator()
        passed, reason = evaluator.evaluate(condition)
        assert not passed
        assert "Platform" in reason

    def test_empty_platforms_passes(self) -> None:
        condition = ConditionConfig(platforms=[])
        evaluator = ConditionEvaluator()
        passed, _ = evaluator.evaluate(condition)
        assert passed


class TestPythonVersionCondition:
    """Tests for Python version conditions."""

    def test_current_version_passes(self) -> None:
        current = f">={sys.version_info.major}.{sys.version_info.minor}"
        condition = ConditionConfig(python_version=current)
        evaluator = ConditionEvaluator()
        passed, _ = evaluator.evaluate(condition)
        assert passed

    def test_future_version_fails(self) -> None:
        condition = ConditionConfig(python_version=">=99.0")
        evaluator = ConditionEvaluator()
        passed, reason = evaluator.evaluate(condition)
        assert not passed
        assert "Python" in reason

    def test_exact_version_match(self) -> None:
        current = f"=={sys.version_info.major}.{sys.version_info.minor}"
        condition = ConditionConfig(python_version=current)
        evaluator = ConditionEvaluator()
        passed, _ = evaluator.evaluate(condition)
        assert passed


class TestEnvConditions:
    """Tests for environment variable conditions."""

    def test_env_set_passes(self) -> None:
        os.environ["PYR_TEST_VAR"] = "value"
        try:
            condition = ConditionConfig(env_set=["PYR_TEST_VAR"])
            evaluator = ConditionEvaluator()
            passed, _ = evaluator.evaluate(condition)
            assert passed
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_set_fails(self) -> None:
        # Ensure var doesn't exist
        os.environ.pop("PYR_NONEXISTENT_VAR", None)
        condition = ConditionConfig(env_set=["PYR_NONEXISTENT_VAR"])
        evaluator = ConditionEvaluator()
        passed, reason = evaluator.evaluate(condition)
        assert not passed
        assert "not set" in reason

    def test_env_not_set_passes(self) -> None:
        os.environ.pop("PYR_NONEXISTENT_VAR", None)
        condition = ConditionConfig(env_not_set=["PYR_NONEXISTENT_VAR"])
        evaluator = ConditionEvaluator()
        passed, _ = evaluator.evaluate(condition)
        assert passed

    def test_env_not_set_fails(self) -> None:
        os.environ["PYR_TEST_VAR"] = "value"
        try:
            condition = ConditionConfig(env_not_set=["PYR_TEST_VAR"])
            evaluator = ConditionEvaluator()
            passed, reason = evaluator.evaluate(condition)
            assert not passed
            assert "should not be set" in reason
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_true_passes(self) -> None:
        for value in ["1", "true", "True", "yes", "on"]:
            os.environ["PYR_TEST_VAR"] = value
            try:
                condition = ConditionConfig(env_true=["PYR_TEST_VAR"])
                evaluator = ConditionEvaluator()
                passed, _ = evaluator.evaluate(condition)
                assert passed, f"Failed for value: {value}"
            finally:
                del os.environ["PYR_TEST_VAR"]

    def test_env_true_fails(self) -> None:
        os.environ["PYR_TEST_VAR"] = "0"
        try:
            condition = ConditionConfig(env_true=["PYR_TEST_VAR"])
            evaluator = ConditionEvaluator()
            passed, _ = evaluator.evaluate(condition)
            assert not passed
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_false_passes(self) -> None:
        os.environ["PYR_TEST_VAR"] = "0"
        try:
            condition = ConditionConfig(env_false=["PYR_TEST_VAR"])
            evaluator = ConditionEvaluator()
            passed, _ = evaluator.evaluate(condition)
            assert passed
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_equals_passes(self) -> None:
        os.environ["PYR_TEST_VAR"] = "expected_value"
        try:
            condition = ConditionConfig(env_equals={"PYR_TEST_VAR": "expected_value"})
            evaluator = ConditionEvaluator()
            passed, _ = evaluator.evaluate(condition)
            assert passed
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_equals_fails(self) -> None:
        os.environ["PYR_TEST_VAR"] = "actual_value"
        try:
            condition = ConditionConfig(env_equals={"PYR_TEST_VAR": "expected_value"})
            evaluator = ConditionEvaluator()
            passed, reason = evaluator.evaluate(condition)
            assert not passed
            assert "expected" in reason
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_contains_passes(self) -> None:
        os.environ["PYR_TEST_VAR"] = "hello world"
        try:
            condition = ConditionConfig(env_contains={"PYR_TEST_VAR": "world"})
            evaluator = ConditionEvaluator()
            passed, _ = evaluator.evaluate(condition)
            assert passed
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_env_contains_fails(self) -> None:
        os.environ["PYR_TEST_VAR"] = "hello"
        try:
            condition = ConditionConfig(env_contains={"PYR_TEST_VAR": "world"})
            evaluator = ConditionEvaluator()
            passed, reason = evaluator.evaluate(condition)
            assert not passed
            assert "contain" in reason
        finally:
            del os.environ["PYR_TEST_VAR"]


class TestFileConditions:
    """Tests for file existence conditions."""

    def test_files_exist_passes(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        condition = ConditionConfig(files_exist=["test.txt"])
        evaluator = ConditionEvaluator(project_root=tmp_path)
        passed, _ = evaluator.evaluate(condition)
        assert passed

    def test_files_exist_fails(self, tmp_path: Path) -> None:
        condition = ConditionConfig(files_exist=["nonexistent.txt"])
        evaluator = ConditionEvaluator(project_root=tmp_path)
        passed, reason = evaluator.evaluate(condition)
        assert not passed
        assert "does not exist" in reason

    def test_files_not_exist_passes(self, tmp_path: Path) -> None:
        condition = ConditionConfig(files_not_exist=["nonexistent.txt"])
        evaluator = ConditionEvaluator(project_root=tmp_path)
        passed, _ = evaluator.evaluate(condition)
        assert passed

    def test_files_not_exist_fails(self, tmp_path: Path) -> None:
        test_file = tmp_path / "test.txt"
        test_file.write_text("content")

        condition = ConditionConfig(files_not_exist=["test.txt"])
        evaluator = ConditionEvaluator(project_root=tmp_path)
        passed, reason = evaluator.evaluate(condition)
        assert not passed
        assert "should not exist" in reason


class TestCombinedConditions:
    """Tests for multiple conditions combined."""

    def test_all_conditions_must_pass(self) -> None:
        os.environ["PYR_TEST_VAR"] = "1"
        try:
            current_platform = (
                "macos" if platform.system() == "Darwin" else platform.system().lower()
            )
            condition = ConditionConfig(
                platforms=[current_platform],
                env_set=["PYR_TEST_VAR"],
            )
            evaluator = ConditionEvaluator()
            passed, _ = evaluator.evaluate(condition)
            assert passed
        finally:
            del os.environ["PYR_TEST_VAR"]

    def test_fails_on_first_unmet_condition(self) -> None:
        # Platform passes, but env var fails
        current_platform = "macos" if platform.system() == "Darwin" else platform.system().lower()
        os.environ.pop("PYR_NONEXISTENT", None)

        condition = ConditionConfig(
            platforms=[current_platform],
            env_set=["PYR_NONEXISTENT"],
        )
        evaluator = ConditionEvaluator()
        passed, reason = evaluator.evaluate(condition)
        assert not passed
        assert "not set" in reason

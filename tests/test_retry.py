"""Tests for retry logic with exponential backoff."""

from __future__ import annotations

import time
from textwrap import dedent
from typing import TYPE_CHECKING

import pytest

from uvtx.config import ConfigError
from uvtx.runner import Runner

if TYPE_CHECKING:
    from pathlib import Path


class TestRetryLogic:
    """Test retry logic with exponential backoff."""

    def test_no_retry_on_success(self, tmp_path: Path) -> None:
        """Test that successful tasks don't trigger retries."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.success]
            cmd = "python -c 'import sys; sys.exit(0)'"
            max_retries = 3
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = Runner.from_config_file(config_path)
        result = runner.run_task("success")

        assert result.success
        assert result.return_code == 0

    def test_retry_with_eventual_success(self, tmp_path: Path) -> None:
        """Test that tasks retry and eventually succeed."""
        # Create a script that fails first time, succeeds second time
        script = tmp_path / "flaky.py"
        counter_file = tmp_path / "counter.txt"
        script.write_text(
            dedent(f"""
                import sys
                from pathlib import Path

                counter_file = Path(r"{counter_file}")
                count = 0
                if counter_file.exists():
                    count = int(counter_file.read_text())

                count += 1
                counter_file.write_text(str(count))

                # Fail on first attempt, succeed on second
                if count == 1:
                    print("Attempt 1: failing")
                    sys.exit(1)
                else:
                    print("Attempt 2: success!")
                    sys.exit(0)
            """)
        )

        config_content = dedent(f"""
            [project]
            name = "test"

            [tasks.flaky]
            cmd = "python {script}"
            max_retries = 2
            retry_backoff = 0.1
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = Runner.from_config_file(config_path)
        start_time = time.time()
        result = runner.run_task("flaky")
        elapsed = time.time() - start_time

        assert result.success
        assert result.return_code == 0
        # Should have waited at least 0.1 seconds for one retry
        assert elapsed >= 0.1
        # Verify it actually ran twice
        assert counter_file.exists()
        assert int(counter_file.read_text()) == 2

    def test_retry_max_attempts_exceeded(self, tmp_path: Path) -> None:
        """Test that retries stop after max_retries."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.always_fails]
            cmd = "python -c 'import sys; sys.exit(1)'"
            max_retries = 2
            retry_backoff = 0.1
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = Runner.from_config_file(config_path)
        start_time = time.time()
        result = runner.run_task("always_fails")
        elapsed = time.time() - start_time

        assert not result.success
        assert result.return_code == 1
        # Should have tried 3 times total (initial + 2 retries)
        # With backoff: 0.1s + 0.2s = 0.3s minimum
        assert elapsed >= 0.3

    def test_retry_on_specific_exit_codes(self, tmp_path: Path) -> None:
        """Test retry only on specific exit codes."""
        # Exit code 2 - should NOT retry (not in list)
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.exit_2]
            cmd = "python -c 'import sys; sys.exit(2)'"
            max_retries = 3
            retry_backoff = 0.1
            retry_on_exit_codes = [1, 124]
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = Runner.from_config_file(config_path)
        start_time = time.time()
        result = runner.run_task("exit_2")
        elapsed = time.time() - start_time

        assert not result.success
        assert result.return_code == 2
        # Should NOT have retried, so very fast
        assert elapsed < 0.2

    def test_retry_exponential_backoff(self, tmp_path: Path) -> None:
        """Test that backoff increases exponentially."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.fails]
            cmd = "python -c 'import sys; sys.exit(1)'"
            max_retries = 3
            retry_backoff = 0.1
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = Runner.from_config_file(config_path)
        start_time = time.time()
        result = runner.run_task("fails")
        elapsed = time.time() - start_time

        assert not result.success
        # Backoff sequence: 0.1s, 0.2s, 0.4s = 0.7s total
        assert elapsed >= 0.7
        # Allow some margin but ensure it's not way too long
        assert elapsed < 1.5

    def test_no_retry_when_max_retries_zero(self, tmp_path: Path) -> None:
        """Test that max_retries=0 means no retry."""
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.no_retry]
            cmd = "python -c 'import sys; sys.exit(1)'"
            max_retries = 0
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        runner = Runner.from_config_file(config_path)
        start_time = time.time()
        result = runner.run_task("no_retry")
        elapsed = time.time() - start_time

        assert not result.success
        # Should be very fast (no retries)
        assert elapsed < 0.2

    def test_retry_validation_limits(self, tmp_path: Path) -> None:
        """Test that retry fields have proper validation."""
        # max_retries should be limited to 0-10
        config_content = dedent("""
            [project]
            name = "test"

            [tasks.invalid]
            cmd = "echo test"
            max_retries = 15
        """)
        config_path = tmp_path / "uvtx.toml"
        config_path.write_text(config_content)

        # Should raise validation error
        with pytest.raises(ConfigError):
            Runner.from_config_file(config_path)

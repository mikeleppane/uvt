"""Performance regression tests for pt task runner.

Tests verify that optimizations maintain expected performance characteristics:
- Config caching provides significant speedup on repeated loads
- O(n) algorithms scale linearly with input size
- Script metadata caching improves repeated parsing
"""

import time
from pathlib import Path
from textwrap import dedent

from pt.config import load_config
from pt.script_meta import parse_script_metadata


class TestConfigCaching:
    """Test that config caching provides meaningful performance improvements."""

    def test_config_cache_hit_faster_than_miss(self, tmp_path: Path) -> None:
        """Cached config load should be significantly faster than initial parse."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo test"
            """)
        )

        # Cold load (cache miss)
        start = time.perf_counter()
        config1, _ = load_config(config_file)
        cold_time = time.perf_counter() - start

        # Warm load (cache hit)
        start = time.perf_counter()
        config2, _ = load_config(config_file)
        warm_time = time.perf_counter() - start

        # Verify same config returned
        assert config1 == config2

        # Cache hit should be at least 5x faster
        # (TOML parsing + Pydantic validation + inheritance resolution overhead)
        assert warm_time < cold_time * 0.2, (
            f"Cache hit ({warm_time:.4f}s) should be much faster than "
            f"cold load ({cold_time:.4f}s)"
        )

    def test_config_cache_invalidation_on_mtime_change(self, tmp_path: Path) -> None:
        """Config cache should invalidate when file is modified."""
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo v1"
            """)
        )

        # Load initial config
        config1, _ = load_config(config_file)
        assert config1.tasks["test"].cmd == "echo v1"

        # Modify file (sleep to ensure mtime changes)
        time.sleep(0.01)
        config_file.write_text(
            dedent("""
                [project]
                name = "test"

                [tasks.test]
                cmd = "echo v2"
            """)
        )

        # Load modified config - should invalidate cache
        config2, _ = load_config(config_file)
        assert config2.tasks["test"].cmd == "echo v2"

    def test_large_config_with_inheritance(self, tmp_path: Path) -> None:
        """Verify caching helps with large configs with deep inheritance."""
        # Create config with 50 tasks, some with inheritance chains
        config_lines = [
            "[project]",
            'name = "test"',
            "",
            "[tasks.base]",
            'cmd = "echo base"',
            "dependencies = ['dep1']",
            "",
        ]

        # Create inheritance chain: base -> task1 -> task2 -> ... -> task49
        for i in range(50):
            extend = "base" if i == 0 else f"task{i-1}"
            config_lines.extend(
                [
                    f"[tasks.task{i}]",
                    f'extend = "{extend}"',
                    f'dependencies = ["dep{i}"]',
                    "",
                ]
            )

        config_file = tmp_path / "pt.toml"
        config_file.write_text("\n".join(config_lines))

        # Cold load
        start = time.perf_counter()
        config1, _ = load_config(config_file)
        cold_time = time.perf_counter() - start

        # Warm load
        start = time.perf_counter()
        _config2, _ = load_config(config_file)
        warm_time = time.perf_counter() - start

        # Verify inheritance was resolved correctly
        # base has dep1, task0-49 each add dep0-49 (50 deps total)
        assert len(config1.tasks["task49"].dependencies) == 50

        # Cache should provide significant speedup
        assert warm_time < cold_time * 0.2


class TestScriptMetadataCaching:
    """Test that PEP 723 metadata caching works correctly."""

    def test_metadata_cache_hit_faster_than_miss(self, tmp_path: Path) -> None:
        """Cached metadata parse should be faster than initial parse."""
        script_file = tmp_path / "script.py"
        script_file.write_text(
            dedent("""
                # /// script
                # dependencies = ["requests", "rich"]
                # requires-python = ">=3.10"
                # ///

                print("hello")
            """)
        )

        # Cold parse (cache miss)
        start = time.perf_counter()
        meta1 = parse_script_metadata(script_file)
        cold_time = time.perf_counter() - start

        # Warm parse (cache hit)
        start = time.perf_counter()
        meta2 = parse_script_metadata(script_file)
        warm_time = time.perf_counter() - start

        # Verify same metadata returned
        assert meta1.dependencies == meta2.dependencies == ["requests", "rich"]

        # Cache hit should be faster (regex + TOML parsing overhead)
        assert warm_time < cold_time * 0.3

    def test_metadata_cache_invalidation_on_mtime_change(self, tmp_path: Path) -> None:
        """Metadata cache should invalidate when script file is modified."""
        script_file = tmp_path / "script.py"
        script_file.write_text(
            dedent("""
                # /// script
                # dependencies = ["requests"]
                # ///

                print("v1")
            """)
        )

        # Parse initial metadata
        meta1 = parse_script_metadata(script_file)
        assert meta1.dependencies == ["requests"]

        # Modify file
        time.sleep(0.01)
        script_file.write_text(
            dedent("""
                # /// script
                # dependencies = ["rich"]
                # ///

                print("v2")
            """)
        )

        # Parse modified metadata - should invalidate cache
        meta2 = parse_script_metadata(script_file)
        assert meta2.dependencies == ["rich"]


class TestAlgorithmicComplexity:
    """Test that O(n) optimizations scale linearly."""

    def test_dependency_merging_scales_linearly(self, tmp_path: Path) -> None:
        """Dependency merging should be O(n), not O(n²)."""
        # Create configs with varying number of dependencies
        times = []

        for size in [10, 50, 100]:
            # Build config with many dependencies
            deps = [f'"dep{i}"' for i in range(size)]
            config_file = tmp_path / f"pt_{size}.toml"
            config_file.write_text(
                dedent(f"""
                    [project]
                    name = "test"

                    [tasks.base]
                    cmd = "echo base"
                    dependencies = [{', '.join(deps)}]

                    [tasks.child]
                    extend = "base"
                    dependencies = [{', '.join(deps)}]
                """)
            )

            # Measure load time (includes dependency merging)
            start = time.perf_counter()
            load_config(config_file)
            elapsed = time.perf_counter() - start
            times.append((size, elapsed))

        # Verify roughly linear scaling (not quadratic)
        # If O(n²), time ratio should be ~100 for 10x size increase
        # If O(n), time ratio should be ~10 for 10x size increase
        small_time = times[0][1]
        large_time = times[2][1]
        ratio = large_time / small_time if small_time > 0 else 0

        # Allow 15x ratio for 10x size increase (accounting for overhead)
        # O(n²) would give ~100x ratio
        assert ratio < 15, (
            f"Scaling appears quadratic: 10x size increase took {ratio:.1f}x longer. "
            f"Times: {times}"
        )

    def test_pythonpath_merging_scales_linearly(self, tmp_path: Path) -> None:
        """PYTHONPATH merging should use set-based deduplication (O(n))."""
        times = []

        for size in [10, 50, 100]:
            # Create many pythonpath entries
            paths = [f'"path{i}"' for i in range(size)]
            config_file = tmp_path / f"pythonpath_{size}.toml"
            config_file.write_text(
                dedent(f"""
                    [project]
                    name = "test"

                    [tasks.base]
                    cmd = "echo base"
                    pythonpath = [{', '.join(paths)}]

                    [tasks.child]
                    extend = "base"
                    pythonpath = [{', '.join(paths)}]
                """)
            )

            # Measure load time
            start = time.perf_counter()
            load_config(config_file)
            elapsed = time.perf_counter() - start
            times.append((size, elapsed))

        # Verify linear scaling
        small_time = times[0][1]
        large_time = times[2][1]
        ratio = large_time / small_time if small_time > 0 else 0

        assert ratio < 15, (
            f"PYTHONPATH merging appears quadratic: 10x size increase took {ratio:.1f}x longer. "
            f"Times: {times}"
        )


class TestRegressionBenchmarks:
    """High-level benchmarks to catch performance regressions."""

    def test_typical_config_load_time(self, tmp_path: Path) -> None:
        """Typical config should load in reasonable time."""
        # Create a realistic config: 20 tasks, some inheritance, dependencies
        config_file = tmp_path / "pt.toml"
        config_file.write_text(
            dedent("""
                [project]
                name = "myproject"
                python = "3.10"

                [tasks.base]
                cmd = "echo base"
                dependencies = ["requests", "rich"]

                [tasks.test]
                extend = "base"
                cmd = "pytest tests/"
                dependencies = ["pytest", "pytest-cov"]

                [tasks.lint]
                cmd = "ruff check src/"
                dependencies = ["ruff"]

                [tasks.format]
                cmd = "ruff format src/"
                dependencies = ["ruff"]

                [tasks.build]
                cmd = "python -m build"
                dependencies = ["build"]

                [tasks.ci]
                depends_on = ["test", "lint"]

                [profiles.dev]
                python = "3.11"

                [profiles.ci]
                python = "3.10"
            """)
        )

        # Cold load should be reasonably fast (< 100ms on modern hardware)
        start = time.perf_counter()
        load_config(config_file)
        cold_time = time.perf_counter() - start

        # Allow 200ms for cold load (conservative, CI systems may be slower)
        assert cold_time < 0.2, f"Config load took {cold_time:.3f}s, expected < 0.2s"

        # Warm load should be very fast (< 5ms)
        start = time.perf_counter()
        load_config(config_file)
        warm_time = time.perf_counter() - start

        assert warm_time < 0.005, f"Cached load took {warm_time:.3f}s, expected < 0.005s"

"""Tests for pt.script_meta."""

from pathlib import Path

from uvtx.script_meta import (
    merge_dependencies,
    parse_script_metadata,
    parse_script_metadata_from_string,
)


class TestParseScriptMetadata:
    """Tests for parsing PEP 723 inline metadata."""

    def test_basic_metadata(self) -> None:
        content = """\
#!/usr/bin/env python3
# /// script
# dependencies = ["requests", "rich"]
# requires-python = ">=3.10"
# ///

import requests
"""
        meta = parse_script_metadata_from_string(content)
        assert meta.dependencies == ["requests", "rich"]
        assert meta.requires_python == ">=3.10"

    def test_no_metadata(self) -> None:
        content = """\
#!/usr/bin/env python3
import sys
print("Hello")
"""
        meta = parse_script_metadata_from_string(content)
        assert meta.dependencies == []
        assert meta.requires_python is None

    def test_empty_dependencies(self) -> None:
        content = """\
# /// script
# dependencies = []
# ///
"""
        meta = parse_script_metadata_from_string(content)
        assert meta.dependencies == []

    def test_only_requires_python(self) -> None:
        content = """\
# /// script
# requires-python = ">=3.11"
# ///
"""
        meta = parse_script_metadata_from_string(content)
        assert meta.dependencies == []
        assert meta.requires_python == ">=3.11"

    def test_version_specifiers(self) -> None:
        content = """\
# /// script
# dependencies = [
#   "requests>=2.0,<3",
#   "pydantic[email]>=2.0",
# ]
# ///
"""
        meta = parse_script_metadata_from_string(content)
        assert "requests>=2.0,<3" in meta.dependencies
        assert "pydantic[email]>=2.0" in meta.dependencies

    def test_invalid_toml(self) -> None:
        content = """\
# /// script
# dependencies = [invalid
# ///
"""
        meta = parse_script_metadata_from_string(content)
        assert meta.dependencies == []

    def test_metadata_in_middle_of_file(self) -> None:
        content = '''\
#!/usr/bin/env python3
"""Module docstring."""

# /// script
# dependencies = ["click"]
# ///

import click
'''
        meta = parse_script_metadata_from_string(content)
        assert meta.dependencies == ["click"]

    def test_from_file(self, tmp_path: Path) -> None:
        script = tmp_path / "test.py"
        script.write_text("""\
# /// script
# dependencies = ["pytest"]
# ///
""")
        meta = parse_script_metadata(script)
        assert meta.dependencies == ["pytest"]

    def test_missing_file(self, tmp_path: Path) -> None:
        script = tmp_path / "nonexistent.py"
        meta = parse_script_metadata(script)
        assert meta.dependencies == []


class TestMergeDependencies:
    """Tests for merging dependencies."""

    def test_simple_merge(self) -> None:
        script_deps = ["requests"]
        config_deps = ["pydantic"]
        result = merge_dependencies(script_deps, config_deps)
        assert result == ["requests", "pydantic"]

    def test_config_overrides_version(self) -> None:
        script_deps = ["requests>=1.0"]
        config_deps = ["requests>=2.0"]
        result = merge_dependencies(script_deps, config_deps)
        assert result == ["requests>=2.0"]

    def test_no_duplicates(self) -> None:
        script_deps = ["requests", "click"]
        config_deps = ["requests", "rich"]
        result = merge_dependencies(script_deps, config_deps)
        assert len([d for d in result if d.startswith("requests")]) == 1
        assert "click" in result
        assert "rich" in result

    def test_extras_handling(self) -> None:
        script_deps = ["pydantic"]
        config_deps = ["pydantic[email]>=2.0"]
        result = merge_dependencies(script_deps, config_deps)
        # Config version with extras should win
        assert "pydantic[email]>=2.0" in result

    def test_empty_inputs(self) -> None:
        assert merge_dependencies([], []) == []
        assert merge_dependencies(["a"], []) == ["a"]
        assert merge_dependencies([], ["b"]) == ["b"]

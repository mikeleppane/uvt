"""Tests for .env file parsing."""

from __future__ import annotations

import os
from textwrap import dedent
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from pathlib import Path

from uvtx.dotenv import _expand_variables, _process_escape_sequences, load_env_file, load_env_files


class TestProcessEscapeSequences:
    """Tests for _process_escape_sequences function."""

    def test_newline_escape(self) -> None:
        """Test processing newline escape sequence."""
        result = _process_escape_sequences("line1\\nline2")
        assert result == "line1\nline2"

    def test_tab_escape(self) -> None:
        """Test processing tab escape sequence."""
        result = _process_escape_sequences("col1\\tcol2")
        assert result == "col1\tcol2"

    def test_carriage_return_escape(self) -> None:
        """Test processing carriage return escape sequence."""
        result = _process_escape_sequences("line1\\rline2")
        assert result == "line1\rline2"

    def test_quote_escape(self) -> None:
        """Test processing escaped quotes."""
        result = _process_escape_sequences('say \\"hello\\"')
        assert result == 'say "hello"'

    def test_backslash_escape(self) -> None:
        """Test processing escaped backslash."""
        # Double backslash becomes single backslash
        result = _process_escape_sequences("path\\\\file")
        assert result == "path\\file"

    def test_multiple_escapes(self) -> None:
        """Test processing multiple escape sequences."""
        result = _process_escape_sequences("line1\\nline2\\ttab\\\\slash")
        assert result == "line1\nline2\ttab\\slash"

    def test_no_escapes(self) -> None:
        """Test processing string with no escapes."""
        result = _process_escape_sequences("plain text")
        assert result == "plain text"


class TestExpandVariables:
    """Tests for _expand_variables function."""

    def test_expand_braced_variable(self) -> None:
        """Test expanding ${VAR} syntax."""
        env = {"FOO": "bar"}
        result = _expand_variables("value is ${FOO}", env)
        assert result == "value is bar"

    def test_expand_simple_variable(self) -> None:
        """Test expanding $VAR syntax."""
        env = {"FOO": "bar"}
        result = _expand_variables("value is $FOO", env)
        assert result == "value is bar"

    def test_expand_multiple_variables(self) -> None:
        """Test expanding multiple variables."""
        env = {"FOO": "bar", "BAZ": "qux"}
        result = _expand_variables("$FOO and ${BAZ}", env)
        assert result == "bar and qux"

    def test_expand_missing_variable(self) -> None:
        """Test expanding non-existent variable returns empty string."""
        env: dict[str, str] = {}
        result = _expand_variables("value is ${MISSING}", env)
        assert result == "value is "

    def test_expand_from_system_env(self) -> None:
        """Test expanding from system environment."""
        os.environ["UVR_TEST_VAR"] = "system_value"
        try:
            env: dict[str, str] = {}
            result = _expand_variables("value is ${UVR_TEST_VAR}", env)
            assert result == "value is system_value"
        finally:
            del os.environ["UVR_TEST_VAR"]

    def test_local_env_overrides_system(self) -> None:
        """Test that local env takes precedence over system env."""
        os.environ["UVR_TEST_VAR"] = "system_value"
        try:
            env = {"UVR_TEST_VAR": "local_value"}
            result = _expand_variables("value is ${UVR_TEST_VAR}", env)
            assert result == "value is local_value"
        finally:
            del os.environ["UVR_TEST_VAR"]

    def test_expand_at_start(self) -> None:
        """Test expansion at start of string."""
        env = {"FOO": "bar"}
        result = _expand_variables("$FOO is the value", env)
        assert result == "bar is the value"

    def test_expand_at_end(self) -> None:
        """Test expansion at end of string."""
        env = {"FOO": "bar"}
        result = _expand_variables("value is $FOO", env)
        assert result == "value is bar"

    def test_no_expansion_needed(self) -> None:
        """Test string with no variables."""
        env = {"FOO": "bar"}
        result = _expand_variables("plain text", env)
        assert result == "plain text"


class TestLoadEnvFile:
    """Tests for load_env_file function."""

    def test_load_simple_file(self, tmp_path: Path) -> None:
        """Test loading simple KEY=value pairs."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                FOO=bar
                BAZ=qux
            """)
        )

        result = load_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_load_with_export_prefix(self, tmp_path: Path) -> None:
        """Test loading with export prefix."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                export FOO=bar
                export BAZ=qux
            """)
        )

        result = load_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_load_with_double_quotes(self, tmp_path: Path) -> None:
        """Test loading double-quoted values."""
        env_file = tmp_path / ".env"
        env_file.write_text('FOO="bar with spaces"\n')

        result = load_env_file(env_file)
        assert result == {"FOO": "bar with spaces"}

    def test_load_with_single_quotes(self, tmp_path: Path) -> None:
        """Test loading single-quoted values."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO='bar with spaces'\n")

        result = load_env_file(env_file)
        assert result == {"FOO": "bar with spaces"}

    def test_load_with_escape_sequences(self, tmp_path: Path) -> None:
        """Test loading with escape sequences in double quotes."""
        env_file = tmp_path / ".env"
        env_file.write_text('FOO="line1\\nline2\\ttab"\n')

        result = load_env_file(env_file)
        assert result == {"FOO": "line1\nline2\ttab"}

    def test_single_quotes_are_literal(self, tmp_path: Path) -> None:
        """Test that single quotes preserve literal values."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO='line1\\nline2'\n")

        result = load_env_file(env_file)
        assert result == {"FOO": "line1\\nline2"}

    def test_load_with_comments(self, tmp_path: Path) -> None:
        """Test loading file with comments."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                # This is a comment
                FOO=bar
                # Another comment
                BAZ=qux
            """)
        )

        result = load_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_load_with_inline_comments(self, tmp_path: Path) -> None:
        """Test loading file with inline comments."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar # inline comment\n")

        result = load_env_file(env_file)
        assert result == {"FOO": "bar"}

    def test_quoted_values_preserve_hashes(self, tmp_path: Path) -> None:
        """Test that quoted values preserve # characters."""
        env_file = tmp_path / ".env"
        env_file.write_text('FOO="value # with hash"\n')

        result = load_env_file(env_file)
        assert result == {"FOO": "value # with hash"}

    def test_load_with_empty_lines(self, tmp_path: Path) -> None:
        """Test loading file with empty lines."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                FOO=bar

                BAZ=qux

            """)
        )

        result = load_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_load_with_variable_expansion(self, tmp_path: Path) -> None:
        """Test variable expansion within file."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                BASE=/home/user
                PATH_1=${BASE}/dir1
                PATH_2=$BASE/dir2
            """)
        )

        result = load_env_file(env_file)
        assert result == {
            "BASE": "/home/user",
            "PATH_1": "/home/user/dir1",
            "PATH_2": "/home/user/dir2",
        }

    def test_load_empty_value(self, tmp_path: Path) -> None:
        """Test loading empty value."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=\n")

        result = load_env_file(env_file)
        assert result == {"FOO": ""}

    def test_load_empty_double_quotes(self, tmp_path: Path) -> None:
        """Test loading empty double-quoted value."""
        env_file = tmp_path / ".env"
        env_file.write_text('FOO=""\n')

        result = load_env_file(env_file)
        assert result == {"FOO": ""}

    def test_load_empty_single_quotes(self, tmp_path: Path) -> None:
        """Test loading empty single-quoted value."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=''\n")

        result = load_env_file(env_file)
        assert result == {"FOO": ""}

    def test_load_nonexistent_file(self, tmp_path: Path) -> None:
        """Test loading non-existent file returns empty dict."""
        result = load_env_file(tmp_path / "nonexistent.env")
        assert result == {}

    def test_invalid_format_skipped(self, tmp_path: Path) -> None:
        """Test that invalid lines are skipped."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                FOO=bar
                INVALID LINE
                BAZ=qux
            """)
        )

        result = load_env_file(env_file)
        assert result == {"FOO": "bar", "BAZ": "qux"}

    def test_variable_name_rules(self, tmp_path: Path) -> None:
        """Test variable name validation."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                FOO=valid
                _BAR=valid
                FOO_BAR=valid
                FOO123=valid
                123FOO=invalid
                FOO-BAR=invalid
            """)
        )

        result = load_env_file(env_file)
        assert "FOO" in result
        assert "_BAR" in result
        assert "FOO_BAR" in result
        assert "FOO123" in result
        assert "123FOO" not in result
        assert "FOO-BAR" not in result

    def test_multiline_value_not_supported(self, tmp_path: Path) -> None:
        """Test that multiline values are not supported (each line parsed separately)."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                FOO=line1
                line2
            """)
        )

        result = load_env_file(env_file)
        # Only the first line is valid
        assert result == {"FOO": "line1"}

    def test_spaces_around_equals(self, tmp_path: Path) -> None:
        """Test handling of spaces around equals sign."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                FOO=bar
                BAZ = qux
            """)
        )

        result = load_env_file(env_file)
        # "BAZ = qux" won't match because spaces around = break the regex
        assert result == {"FOO": "bar"}

    def test_complex_example(self, tmp_path: Path) -> None:
        """Test complex .env file with multiple features."""
        env_file = tmp_path / ".env"
        env_file.write_text(
            dedent("""\
                # Application config
                APP_NAME=MyApp
                APP_ENV=development

                # Database
                DB_HOST=localhost
                DB_PORT=5432
                export DB_URL="postgresql://${DB_HOST}:${DB_PORT}/mydb"

                # Paths
                BASE_DIR=/home/user
                DATA_DIR=${BASE_DIR}/data
                LOG_DIR=$BASE_DIR/logs

                # Features
                DEBUG=true
                VERBOSE=false # Inline comment

                # Special characters
                MESSAGE="Hello\\nWorld"
                LITERAL='Value with $VAR'
            """)
        )

        result = load_env_file(env_file)
        assert result["APP_NAME"] == "MyApp"
        assert result["APP_ENV"] == "development"
        assert result["DB_HOST"] == "localhost"
        assert result["DB_PORT"] == "5432"
        assert result["DB_URL"] == "postgresql://localhost:5432/mydb"
        assert result["BASE_DIR"] == "/home/user"
        assert result["DATA_DIR"] == "/home/user/data"
        assert result["LOG_DIR"] == "/home/user/logs"
        assert result["DEBUG"] == "true"
        assert result["VERBOSE"] == "false"
        assert result["MESSAGE"] == "Hello\nWorld"
        # Single quotes preserve literal values but variables are still expanded
        # since expansion happens after quote removal
        assert result["LITERAL"] == "Value with "


class TestLoadEnvFiles:
    """Tests for load_env_files function."""

    def test_load_single_file(self, tmp_path: Path) -> None:
        """Test loading a single .env file."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        result = load_env_files([".env"], tmp_path)
        assert result == {"FOO": "bar"}

    def test_load_multiple_files(self, tmp_path: Path) -> None:
        """Test loading multiple .env files."""
        env1 = tmp_path / ".env.base"
        env1.write_text("FOO=bar\nBAZ=qux\n")

        env2 = tmp_path / ".env.override"
        env2.write_text("FOO=overridden\nNEW=value\n")

        result = load_env_files([".env.base", ".env.override"], tmp_path)
        assert result == {"FOO": "overridden", "BAZ": "qux", "NEW": "value"}

    def test_later_files_override_earlier(self, tmp_path: Path) -> None:
        """Test that later files override earlier files."""
        env1 = tmp_path / ".env.1"
        env1.write_text("FOO=first\nBAR=from_first\n")

        env2 = tmp_path / ".env.2"
        env2.write_text("FOO=second\n")

        result = load_env_files([".env.1", ".env.2"], tmp_path)
        assert result["FOO"] == "second"
        assert result["BAR"] == "from_first"

    def test_absolute_path(self, tmp_path: Path) -> None:
        """Test loading with absolute path."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        result = load_env_files([str(env_file.absolute())], tmp_path)
        assert result == {"FOO": "bar"}

    def test_relative_path(self, tmp_path: Path) -> None:
        """Test loading with relative path."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        result = load_env_files([".env"], tmp_path)
        assert result == {"FOO": "bar"}

    def test_subdirectory_path(self, tmp_path: Path) -> None:
        """Test loading from subdirectory."""
        subdir = tmp_path / "config"
        subdir.mkdir()
        env_file = subdir / ".env"
        env_file.write_text("FOO=bar\n")

        result = load_env_files(["config/.env"], tmp_path)
        assert result == {"FOO": "bar"}

    def test_nonexistent_file_skipped(self, tmp_path: Path) -> None:
        """Test that nonexistent files are skipped."""
        env_file = tmp_path / ".env"
        env_file.write_text("FOO=bar\n")

        result = load_env_files([".env", "nonexistent.env"], tmp_path)
        assert result == {"FOO": "bar"}

    def test_empty_file_list(self, tmp_path: Path) -> None:
        """Test loading empty file list."""
        result = load_env_files([], tmp_path)
        assert result == {}

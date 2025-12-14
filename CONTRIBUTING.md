# Contributing to pt

Thank you for your interest in contributing! This guide will help you set up your development environment and understand our development workflow.

## Prerequisites

- **Python 3.10 or later**
- **[uv](https://docs.astral.sh/uv/)** package manager

## Development Setup

### 1. Clone the repository

```bash
git clone https://github.com/your-username/pt.git
cd pt
```

### 2. Install dependencies with uv

```bash
# Install all dependencies including dev tools
uv sync --all-extras

# Or install pt in editable mode
uv pip install -e .[dev]
```

### 3. Install pre-commit hooks

```bash
uv run pre-commit install

# Optional: Run against all files to verify setup
uv run pre-commit run --all-files
```

### 4. Verify installation

```bash
# Run tests
uv run pytest tests/

# Run linting
uv run ruff check src/ tests/

# Run type checking
uv run mypy src/

# Run all checks (what CI runs)
uv run pytest tests/ && \
uv run ruff format --check src/ tests/ && \
uv run ruff check src/ tests/ && \
uv run mypy src/
```

## Development Workflow

### Code Style

We use:

- **Ruff** for formatting and linting (configured in [pyproject.toml](pyproject.toml))
- **Mypy** for static type checking (strict mode)
- **Pytest** with pytest-asyncio for testing

Pre-commit hooks will automatically run ruff format, ruff check, and mypy before each commit.

### Running Tests

```bash
# Run all tests
uv run pytest tests/

# Run with coverage
uv run pytest tests/ --cov=src/pt --cov-report=term-missing

# Run specific test file
uv run pytest tests/test_config.py

# Run with verbose output
uv run pytest tests/ -v

# Run tests matching a pattern
uv run pytest tests/ -k "test_inheritance"
```

### Manual Linting

```bash
# Format code
uv run ruff format src/ tests/

# Lint with auto-fix
uv run ruff check --fix src/ tests/

# Type check
uv run mypy src/
```

### Using pt in Development

Since pt is installed in editable mode, you can test changes immediately:

```bash
# Run pt from the development version
uv run pt run <task>

# Or activate the virtual environment
source .venv/bin/activate
pt run <task>
```

### Testing pt.toml Changes

You can use the pt project itself for testing:

```bash
# pt has its own pt.toml for self-hosting
uv run pt list
uv run pt check
```

## Project Structure

```
pt/
├── src/pt/              # Source code
│   ├── cli.py           # Click CLI commands
│   ├── config.py        # Config loading and inheritance
│   ├── runner.py        # Task execution orchestration
│   ├── executor.py      # UV command building
│   ├── parallel.py      # Async parallel execution
│   ├── graph.py         # Dependency graph (DAG)
│   ├── models.py        # Pydantic schemas
│   ├── script_meta.py   # PEP 723 parser
│   ├── dotenv.py        # .env file parsing
│   ├── watch.py         # File watching
│   └── completion.py    # Shell completion logic
├── tests/               # Test suite
│   ├── test_*.py        # Test files
│   └── fixtures/        # Test fixtures
├── completion/          # Shell completion scripts
│   ├── pt-completion.bash
│   ├── pt-completion.zsh
│   └── pt.fish
├── .github/workflows/   # CI/CD pipelines
├── pyproject.toml       # Project configuration
├── pt.toml              # pt's own task definitions
└── README.md            # User documentation
```

## Writing Tests

Follow the existing patterns:

```python
from pathlib import Path
from textwrap import dedent
import pytest

def test_example(tmp_path: Path) -> None:
    """Test description."""
    config_file = tmp_path / "pt.toml"
    config_file.write_text(
        dedent("""
        [project]
        name = "test"

        [tasks.hello]
        cmd = "echo hello"
        """)
    )

    # Your test logic
    from pt.config import load_config
    config, path = load_config(config_file)
    assert config.project.name == "test"
```

**Key patterns**:

- Use `tmp_path` fixture for file operations
- Use `textwrap.dedent()` for TOML content
- Use type hints on all functions
- Follow pytest conventions (descriptive names, clear assertions)
- Use `monkeypatch` fixture to change directories or mock functions

## Submitting Changes

### 1. Create a feature branch

```bash
git checkout -b feature/your-feature-name
```

### 2. Make your changes and commit

```bash
git add .
git commit -m "feat: your feature description"
# Pre-commit hooks run automatically
```

**Commit message conventions**:

- `feat:` New feature
- `fix:` Bug fix
- `docs:` Documentation changes
- `test:` Adding or updating tests
- `refactor:` Code refactoring
- `chore:` Maintenance tasks

### 3. Push and create a PR

```bash
git push origin feature/your-feature-name
```

Then create a Pull Request on GitHub.

### 4. CI will automatically:

- Run tests on Python 3.10, 3.11, 3.12, 3.13
- Check formatting, linting, and type hints
- Report coverage

## Release Process

Releases are automated via GitHub Actions:

1. Update version in `src/pt/__init__.py`
2. Update `CHANGELOG.md` (if exists)
3. Create and push a tag:

```bash
git tag v0.2.0
git push origin v0.2.0
```

4. GitHub Actions will:
   - Run full test suite
   - Build distributions
   - Publish to PyPI (requires PyPI trusted publisher setup)
   - Create GitHub release

## Code of Conduct

- Be respectful, inclusive, and constructive
- Focus on what's best for the project and community
- Welcome newcomers and be patient with questions
- Provide constructive feedback

## Questions?

- Open an issue for bugs or feature requests
- Start a discussion for questions
- Check existing issues before creating new ones

## Additional Resources

- [uv documentation](https://docs.astral.sh/uv/)
- [Click documentation](https://click.palletsprojects.com/)
- [Pydantic documentation](https://docs.pydantic.dev/)
- [pytest documentation](https://docs.pytest.org/)

Thank you for contributing to pt!

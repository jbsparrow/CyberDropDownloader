# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

CyberDrop-DL is a bulk asynchronous downloader for multiple file hosts, written in Python 3.11+. It uses Poetry for dependency management and features a TUI interface for user interaction.

## Development Commands

### Setup
```bash
poetry install  # Install dependencies
```

### Testing
```bash
poetry run pytest tests/ -v --cov  # Run all tests with coverage
poetry run pytest tests/test_file.py::test_function  # Run specific test
poetry run tox  # Run tests across multiple Python versions
```

### Linting & Formatting
```bash
poetry run ruff check .  # Lint code
poetry run ruff format .  # Format code
pre-commit run --all-files  # Run pre-commit hooks
```

### Building & Packaging
```bash
poetry build  # Build package
```

## Architecture

### Core Components
- **Director** (`cyberdrop_dl/director.py`): Main orchestration class that manages the entire program lifecycle
- **Manager** (`cyberdrop_dl/managers/manager.py`): Central manager coordinating all subsystems
- **ScrapeMapper** (`cyberdrop_dl/scraper/scrape_mapper.py`): Maps URLs to appropriate crawlers

### Key Directories
- `cyberdrop_dl/crawlers/`: Site-specific crawler implementations (100+ supported sites)
- `cyberdrop_dl/managers/`: Resource managers (config, path, log, progress, etc.)
- `cyberdrop_dl/ui/`: Terminal user interface components
- `cyberdrop_dl/utils/`: Utility functions and helpers
- `cyberdrop_dl/config/`: Configuration models and validation

### Configuration System
Uses Pydantic models for type-safe configuration:
- `config_model.py`: Main settings model
- `auth_model.py`: Authentication settings
- YAML configuration files with validation

### Async Architecture
Built on asyncio with:
- Async HTTP clients using aiohttp
- Async database operations with aiosqlite
- Concurrent downloading and scraping

## Testing Strategy
- Pytest with asyncio support
- Coverage reporting
- Multi-platform testing (Ubuntu, Windows, macOS)
- Multi-Python version testing (3.11, 3.13, PyPy)

## Code Style
- **Ruff** for linting and formatting
- **Google-style** docstrings
- **120 character** line length
- **Type hints** throughout
- **Async/await** pattern for I/O operations

## Important Files
- `pyproject.toml`: Project configuration and dependencies
- `tox.ini`: Multi-environment test configuration
- `.pre-commit-config.yaml`: Pre-commit hooks configuration
- `.github/workflows/ci.yml`: CI/CD pipeline configuration
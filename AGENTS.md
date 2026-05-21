# Xplora - AGENTS.md

This file provides guidelines for agentic coding agents working with this repository.

## Project Overview

Xplora is a web application that allows users to explore and visualize their Twitter data backups. It provides interactive visualization with filtering and media exploration capabilities.

## Build/Lint/Test Commands

### Build Commands:
- `python -m venv venv && source venv/bin/activate && pip install -r requirements.txt` - Install Python dependencies
- `uvicorn main:app --host 0.0.0.0 --port 8000` - Run the single-port app server
- `docker buildx build -t sunbear73/xplora:latest .` - Build the distribution image
- `npm install -g serve` - Optional: install serve for alternate frontend hosting
- `npm install` - Install Node.js dependencies

### Lint Commands:
- `flake8 main.py` - Run Python linter on main.py
- `black main.py` - Format Python code
- `prettier --check index.html` - Check HTML formatting

### Test Commands:
- `python -m pytest` - Run Python tests if any
- `python main.py` - Run backend server (no tests available)
- `python -m py_compile main.py` - Quick Python syntax check
- To run a single test file: `python -m pytest tests/ -k "<test_name>"` (if tests exist)

## Data Policy

- Commit the compact default archive at `public/tweets.js.gz`.
- Do not commit raw `public/tweets.js`, extracted Twitter archives, media caches,
  logs, pid files, scratch analysis output, or `node_modules`.
- Docker builds should include the compressed archive and exclude volatile user
  data via `.dockerignore`.

## Code Style Guidelines

### Python:
- Follow PEP 8 style guide
- Use 4 spaces for indentation
- Variable naming: snake_case for variables, PascalCase for classes
- Function naming: snake_case for functions
- Docstring format: Google-style or Sphinx
- Import order: standard library, third-party, local
- Use type hints where appropriate
- Avoid wildcard imports (from module import *)

### JavaScript/HTML:
- Follow ES6+ standards
- Use const/let instead of var
- Arrow functions for callbacks
- Properly format JSX with consistent indentation
- Single quotes for strings
- No semicolons
- Use descriptive variable names

### Error Handling:
- Use try/catch blocks for operations that may fail
- Handle file reading/writing errors gracefully
- Validate API inputs
- Log errors appropriately with logging library
- Return appropriate HTTP status codes in API endpoints

### Naming Conventions:
- Use descriptive names for functions and variables
- Avoid abbreviations unless they're commonly understood
- Use full words in variable names (e.g., `tweet_count` instead of `tc`)
- Keep function names concise but descriptive
- Use consistent naming across the codebase

### Imports:
- Group imports in order: standard library, third-party, local
- Import modules at the top of the file
- Prefer absolute imports over relative imports where possible
- Use proper import aliasing for long module names

### Formatting:
- Keep lines under 88 characters for Python
- Use consistent spacing
- Place blank lines between logical sections in functions
- Use docstrings for all public functions
- Align multi-line function parameters and arguments

### Documentation:
- Add docstrings for all public functions
- Comment complex code sections
- Update README.md when making API changes
- Use semantic versioning for releases

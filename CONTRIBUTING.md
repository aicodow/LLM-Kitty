# Contributing to Kitty

Thank you for your interest in contributing to Kitty! We welcome contributions from everyone.

## Code of Conduct

This project adheres to the [Contributor Covenant](CODE_OF_CONDUCT.md). By participating, you are expected to uphold this code.

## Getting Started

1. **Fork** the repository on GitHub.
2. **Clone** your fork:
   ```bash
   git clone https://github.com/your-username/kitty.git
   cd kitty
   ```
3. **Install** in development mode:
   ```bash
   pip install -e ".[dev]"
   ```
4. **Create a branch**:
   ```bash
   git checkout -b feature/your-feature-name
   ```

## Development Workflow

### Code Style

- Format: `ruff format src/kitty/ tests/`
- Lint: `ruff check src/kitty/ tests/`
- Types: `mypy src/kitty/`
- All three must pass before committing.

Run all at once:
```bash
make lint typecheck
```

### Testing

```bash
# Run all tests
make test

# Run with coverage
make test-cov

# Run specific test file
pytest tests/unit/test_config.py -v

# Run by marker
pytest -m integration
```

### Conventional Commits

We follow the [Conventional Commits](https://www.conventionalcommits.org/) specification:

```
<type>(<scope>): <description>

feat(providers): add Google Gemini provider
fix(scheduler): resolve rate limiter deadlock
refactor(evaluator): extract ProgressBarManager
test(assertions): add contains assertion tests
docs(api): update REST API reference
perf(cache): switch to diskcache backend
```

Allowed types: `feat`, `fix`, `refactor`, `test`, `docs`, `perf`, `chore`, `security`, `ci`.

## Pull Request Process

1. Ensure all tests pass and linting is clean.
2. Update documentation if you change public APIs.
3. Add tests for new functionality.
4. Keep PRs focused on a single concern.
5. Reference any related issues in the PR description.

### PR Title Format

```
type(scope): brief description

Examples:
  feat(redteam): add memory poisoning plugin
  fix(server): handle None pass_rate in API response
```

### Review Checklist

- [ ] Code follows project style (ruff, mypy)
- [ ] Tests cover both success and failure paths
- [ ] Public APIs have Google-style docstrings
- [ ] No secrets or credentials in code
- [ ] Database migrations are backward compatible

## Project Structure

```
src/kitty/
├── cli/           # Typer CLI commands
├── config/        # YAML configuration loader
├── pipeline/      # Evaluation pipeline (5 Rails)
├── providers/     # LLM provider adapters
├── assertions/    # Assertion engine
├── redteam/       # Red-team plugins & strategies
├── database/      # SQLAlchemy ORM models
├── cache/         # Disk + Redis caching
├── scheduler/     # Rate limiting & concurrency
├── tracing/       # OpenTelemetry integration
├── server/        # FastAPI REST API
├── mcp/           # MCP protocol server
└── types/         # Pydantic schemas
```

## Adding a New Provider

1. Create `src/kitty/providers/<name>.py` implementing `BaseProvider`.
2. Register in `providers/registry.py` via `_lazy_import`.
3. Add tests in `tests/providers/`.
4. Add environment variables to `kitty/types/env.py`.

## Adding a New Plugin

1. Add a YAML entry in `redteam/plugins/builtin/<category>/_manifest.yaml`.
2. Or create a Python plugin class extending `RedteamPluginBase`.
3. Verify it works with both OpenAI and Anthropic providers.
4. Add effectiveness tests in `tests/redteam/`.

## Questions?

Open a [GitHub Discussion](https://github.com/your-org/kitty/discussions) or join our community chat.

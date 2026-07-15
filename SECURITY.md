# Security Policy

## Supported Versions

| Version | Supported          |
|---------|--------------------|
| 0.1.x   | :white_check_mark: |
| < 0.1   | :x:                |

## Reporting a Vulnerability

Kitty takes security seriously. If you discover a security vulnerability, please **do not** open a public issue.

**Instead, report via email**: security@kitty.dev

We will acknowledge receipt within 48 hours and provide a timeline for resolution.

### What to include

- Type of issue (e.g., command injection, API key exposure, path traversal)
- Full paths of source files related to the issue
- Step-by-step reproduction instructions
- Proof-of-concept or exploit code (if applicable)
- Impact assessment

### Scope

- Core framework code in `src/kitty/`
- Configuration loading (`config/loader.py`)
- Provider API key handling
- Database storage of secrets
- CI/CD pipeline definitions

### Out of scope

- Third-party LLM provider API vulnerabilities
- Issues in Promptfoo (the reference project) that do not affect Kitty
- Dependency CVEs already tracked by `pip-audit`

## Disclosure Policy

We follow coordinated disclosure:

1. Reporter submits vulnerability via email
2. Kitty maintainers acknowledge and triage within 48 hours
3. Fix is developed and tested privately
4. Patch is released with advisory notes
5. Reporter is credited (if desired) after public disclosure

## Security Measures in Kitty

- **API Key protection**: Keys use `AES-256-GCM` at rest; `SHA-256` hashing in cache keys; never logged
- **YAML safety**: `SafeYamlLoader` with `MAX_ALIAS_DEPTH=10` prevents Billion Laughs attacks
- **Path traversal**: `safe_resolve_path()` validates file references against allowed roots
- **SQL injection**: SQLAlchemy parameterized queries — no string concatenation
- **Dependency audit**: CI runs `pip-audit` on every PR
- **Log sanitization**: `structlog` processors strip credentials from log output

## Running a Security Audit

```bash
pip install pip-audit bandit
pip-audit
bandit -r src/kitty/ -x src/kitty/tests/
```

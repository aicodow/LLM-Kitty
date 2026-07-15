---
name: Pull Request
about: Submit a pull request to improve Kitty
title: "type(scope): brief description"
labels: ''
assignees: ''
---

## Summary

<!-- One or two sentences describing the change. -->

## Related Issues

<!-- Closes #123, #456 -->

## Type of Change

- [ ] feat: new feature
- [ ] fix: bug fix
- [ ] refactor: code restructuring
- [ ] test: adding or modifying tests
- [ ] docs: documentation updates
- [ ] perf: performance improvement
- [ ] chore: build/tooling
- [ ] security: security fix

## Test Plan

<!-- How did you test this change? -->

- [ ] Unit tests added/updated
- [ ] Integration tests pass
- [ ] Manual testing performed
- [ ] CLI command tested: `kitty eval -c test_config.yaml --no-cache`

## Checklist

- [ ] Code follows project style (`ruff format` + `ruff check`)
- [ ] Type annotations complete (`mypy src/kitty/` passes)
- [ ] Google-style docstrings on public APIs
- [ ] Tests cover both success and failure paths
- [ ] No secrets, credentials, or hardcoded keys
- [ ] Backward compatible (or documented breaking changes)
- [ ] Documentation updated if public API changed
- [ ] CI is green

## Additional Context

<!-- Performance implications, alternative approaches considered, etc. -->

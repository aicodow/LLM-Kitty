---
name: Bug Report
about: Create a report to help us improve Kitty
title: "[BUG] "
labels: bug
assignees: ''
---

## Description

A clear and concise description of what the bug is.

## To Reproduce

Steps to reproduce the behavior:

1. Kitty config used (sanitize API keys):
   ```yaml
   # your kittyconfig.yaml (minimal reproduction)
   ```

2. Command run:
   ```bash
   kitty eval -c kittyconfig.yaml --no-cache
   ```

3. Full error output:
   ```
   paste error here
   ```

## Expected Behavior

A clear and concise description of what you expected to happen.

## Environment

- OS: [e.g. Ubuntu 24.04, macOS 15, Windows 11]
- Python version: [e.g. 3.12.0]
- Kitty version: `pip show kitty-redteam`
- Provider: [e.g. openai:chat:gpt-4.1, anthropic:messages:claude-sonnet-4-20250514]

## Additional Context

- Log level output (`LOG_LEVEL=debug kitty eval ...`)
- Cache directory contents (`ls -la ~/.kitty/cache/`)
- Database file (`file ~/.kitty/kitty.db`)

## Checklist

- [ ] I have removed all API keys and secrets from the reproduction
- [ ] I have verified this is not a known issue
- [ ] I have included the minimal config needed to reproduce

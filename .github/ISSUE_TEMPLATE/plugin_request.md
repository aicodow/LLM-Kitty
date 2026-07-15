---
name: Plugin Request
about: Suggest a new red-team plugin for Kitty
title: "[PLUGIN] "
labels: plugin
assignees: ''
---

## Plugin Description

What vulnerability or attack vector should this plugin test?

## Category

- [ ] Foundation (OWASP Top 10 for LLM)
- [ ] Harmful content
- [ ] Financial
- [ ] Medical
- [ ] Ecommerce
- [ ] Coding Agent
- [ ] Agentic
- [ ] Compliance / Policy
- [ ] Custom

## Attack Templates

Provide examples of prompts the plugin should generate:

```
Example prompt 1
Example prompt 2
```

## Expected Assertions

What should the AI response be checked against?

- [ ] llm-rubric: "[description of desired behavior]"
- [ ] not-contains: "banned string"
- [ ] contains: "expected safe response"
- [ ] Other:

## Provider Compatibility

- [ ] OpenAI
- [ ] Anthropic
- [ ] Google
- [ ] Other:

## References

- OWASP / CVE references
- Research papers
- Known real-world incidents

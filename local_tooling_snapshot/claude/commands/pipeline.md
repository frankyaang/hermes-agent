---
description: Route a coding task through Opus planning, GPT-5.5 execution, and GPT-5.5 audit
allowed-tools: Bash(/Users/frank/pipeline/pipeline.sh *)
---

Run this request through the local three-stage pipeline. Do not implement the task directly in this Claude Code session.

Routing rules:
- Claude Opus 4.7 is only allowed for planning and task decomposition.
- GPT-5.5 with xhigh reasoning performs all code edits, command execution, and tests.
- GPT-5.5 with high reasoning performs audit and final evaluation.
- Do not use Opus for execution, file edits, tests, or code review.

Execute:

```bash
/Users/frank/pipeline/pipeline.sh "$ARGUMENTS" "$(pwd)"
```

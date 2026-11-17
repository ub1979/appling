# Appling C

This is an independent repository. It must not import or require the original
Appling/Hermes checkout. Preserve the copied interface and visual style.

Appling owns requirements, approvals, workflow state, project memory and QA
evidence. Execution engines own model conversations and tools. Never infer task
completion from report prose or let a model change controller approvals.

Keep prompts and tool definitions stable within a session. New models and new
instruction versions get new sessions and compact project handoffs. Store
credentials in environment variables or the CLI's own credential store.

Use `python -m pytest tests` and `cd ui && npm test && npm run build`.
Test behavior, real temporary project files and recovery, not source text.
Never mark UI QA passed without browser evidence. Document blocked validation.

Maintain provenance for reused code and skills in THIRD_PARTY_NOTICES.md.

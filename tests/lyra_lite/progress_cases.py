"""Small ledgers retaining the layouts and stale statuses from the live audit."""

CLAUDE_DELIVERED = """# Pocket Tasks — progress ledger
Current phase: Development

| # | Phase | Agent | Status | Evidence / notes |
|---|---|---|---|---|
| 1 | Development | Dev | running | Development complete. |
| 2 | Quality assurance | QA | round 1 FAIL | First campaign |
| 3 | Quality assurance | QA | round 2 PASS | Repairs verified |
| — | Baseline | — | handed off 2026-10-23 | Owner accepted |

## v2 feature delta — Task priorities
| # | Phase | Agent | Status | Evidence / notes |
|---|---|---|---|---|
| v2-1 | Development | Dev | running | Old implementation update |
| v2-2 | Quality assurance | QA | PASS — nothing blocking | Feature verified |
| — | v2 delta | — | delivered 2026-10-23 | Owner accepted |
"""

HERMES_DELIVERED = """# Progress ledger
| Date | Phase | Status | Notes |
|---|---|---|---|
| 2026-10-23 | build | done (verified) | Built |
| 2026-10-23 | Rev 2 build | running | Old update |
| 2026-10-23 | Rev 2 owner preview | layout repair in flight | Old feedback |
| 2026-10-23 | Rev 2 independent QA | PASS | All checks passed |
| 2026-10-23 | Rev 2 owner approval + delivery | done (delivered) | Owner accepted |
"""

NEW_FEATURE = """
## New feature
| Phase | Status | Evidence |
|---|---|---|
| Export development | running | Remaining implementation |
| Export QA | pending | After implementation |
"""

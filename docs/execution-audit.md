# Planner and role execution audit

Date: 18 November 2026. Status: tested patch prepared in an isolated copy;
not installed into the running `/Users/u/funcoding/appling_c` checkout.

## Confirmed cause

The task-planner skill prescribed 1–3 large tasks for personal projects and
described packages nested inside those tasks. The scheduler executes only the
returned task-array entries; it cannot fan out Markdown packages. The workflow
accepted valid but fully serial dependency graphs and empty ownership. Its
legacy ownership assessment cannot remove dependencies or split an existing
task, so it cannot repair a three-task serial chain by assigning files alone.

## Changes prepared

- Replace the planner's copied workflow with the actual controller contract.
  Every package must be a scheduled task with owned paths and real dependencies.
- Validate new plans with the same selection logic used by the real scheduler.
  Require ownership for all tasks, capacity for two workers, and at least one
  actual parallel wave. Give one correction pass, then pause invalid plans.
- Show the computed schedule in the revision-bound plan review document.
- Add `/replan` for stopped/idle projects. Preserve source, previous task history,
  requirements and prototype approvals; require a new implementation approval.
  Reject races with active workers and changed requirement/prototype revisions.
- Check all 48 original bundled skill prompts and supporting Markdown for stale
  execution rules. Remove the copied second orchestrator; retain one Python
  workflow controller. Adapt legacy skill-loader/delegation/setup instructions
  to native engine/file tools and the bundled script locations.
- Remove stale 10/15-worker claims, fixed task/round/file thresholds, missing
  mandatory process/design files, recursive researcher loading and unnecessary
  per-section commits/build campaigns. Clarify that the host owns Git snapshots.
- Scope QA/review/deployment/documentation to approved behavior and actual risk.
  Keep QA read-only against application source and preserve real browser evidence.
- Keep system instructions stable when runtime capacity changes; put capacity
  in the task briefing. Instruction changes select a new session fingerprint
  through the existing engine-session mechanism.

The common execution contract applies to every role, including specialized
frontend/mobile/design guides. It gives approved project choices precedence
over optional style and process prescriptions.

## Controls deliberately retained

Owner approvals, explicit provider/model selection, authentication and secret
handling, file ownership, isolated worktrees, cancellation, integration conflict
checks, actual configured worker limits and provider budgets remain enforced.
Independent QA checks the integrated revision. Shared foundations/integration
and small follow-up fixes can still run with one worker; a new whole-app plan
must contain useful parallel execution.

Managed Codex workers remain separate native app-server sessions. Nested writable
agents remain disabled so cancellation, ownership and the configured host limit
stay enforceable. Other provider adapters are retained. Legacy JSON response
field names used by the preserved interface remain compatibility fields; they
do not load a Hermes runtime. Hermes references in React Native performance
guidance name React Native's JavaScript engine and are intentionally retained.
Third-party attribution/licences are preserved.

## Validation

The complete Python suite passed: **104 tests**. It uses real temporary project
stores and Git worktrees, protocol/subprocess fixtures, two concurrent workers,
integration, independent QA, correction/rejection of bad plans, revision-bound
approvals, replanning and stable prompt instructions across capacity changes.

Additional checks resolve all bundled skill links through the actual full-skill
reader and verify that the patch applies cleanly to the inspected checkout.
No frontend source changed. Live model planning, live provider acceptance,
phone pairing and a browser walkthrough of the studio were not performed.

An early full-suite run lacked copied UI assets/templates in the isolated test
folder; those fixture-environment omissions were corrected before the complete
passing run. No changes were made to the live project or server.

## Reusable blocks

The planner checks a reusable-block catalogue when one is explicitly supplied;
it must not pretend an absent catalogue exists. See `reusable-blocks.md` for
the proposed package/contract/evidence/versioning design. Catalogue storage,
extraction, publishing, installation and cross-project reuse are future work,
not claims made by this execution patch.

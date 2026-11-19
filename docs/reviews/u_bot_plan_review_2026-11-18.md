# u_bot implementation plan review — 18 November 2026

Recommendation: request changes before approving this revision. Feature coverage and the dependency graph are broadly sound, but execution does not enforce several promises made in the plan.

## Reviewed state

- Project: `2a2446b9bab2`, `u_bot`; phase `plan_review`, not running, plan review pending.
- Approved requirements and prototype hashes still match their files. The pending review matches the current plan.
- All 13 task entries parse successfully. Dependencies are acyclic, and the computed concurrent batches have disjoint assigned paths.
- Current schedule: contracts; browser/WhatsApp/speech; productivity/social/workflows; briefings/meetings/data; UI; integration; QA. Maximum concurrency defaults to three.
- Native nested Codex workers remain disabled. Host-managed parallel workers are the intended execution mechanism.

## Corrections required

### 1. Enforce the same task safeguards for single and parallel execution

`appling/swarm.py:build_ready` sends a single task directly to the main project. It accepts `status=completed` without validating the checks/evidence list or applying the ownership checks used by isolated workers. This affects contracts, UI, integration and the planned QA batch.

A behavioral reproduction using a temporary Store, temporary project and fake engine demonstrated that an unassigned file could be written and the task marked done with no checks at all. No live project state was used or modified.

Required correction: use isolated task workspaces and the same ownership, protected-input, passing-check and evidence validation for every task, including batches of one. Keep integration controller-owned and preserve recovery behavior.

### 2. Make the planned independent QA genuinely independent

The structured `rp-qa` task has role `sw-developer`. The live team contains only `req-engineer` and `task-planner`; changing the task role alone would still encounter the scheduler's fallback to `sw-developer`. A single task uses a role-based session key, so `rp-qa` can resume the implementation session. It is not dispatched with source-read-only enforcement.

A separate temporary-project reproduction demonstrated a QA-labelled task resuming the developer session with `readonly=false` and no isolated worker. The later controller QA phase still exists; this finding concerns the independent QA promised by `rp-qa`.

Required correction: assign an explicit QA role supported by the runtime, create a separate reviewer session, and enforce that application source cannot change while allowing acceptance tests/evidence in their assigned paths. A changed source revision must invalidate verification. Keep defect repair in development tasks. Alternatively, put final acceptance exclusively in the controller's independent QA stage with an explicit evidence contract instead of scheduling it as a developer task.

### 3. Specify the connection from bot requests to real operations

The current generated application uses text-only provider execution in `src/core/tasks.ts`. CLI tools are disabled in `src/providers/cli.ts`, and provider output is text plus a receipt. The plan lists feature factories, routes and integration, but does not explicitly define the bounded execution protocol that turns a bot request into source collection, browser work, a reviewed action, observation and continuation.

This is an implementation-plan ambiguity, not evidence that the future integration cannot implement it. Adding adapters alone would leave the main chat journey incomplete.

Required correction: make the integration deliverable explicitly include typed, validated model/controller operations; allowlisted tool dispatch; task/account authorization; bounded steps; cancellation/recovery; and review/resume. Prove a complete chat-to-operation journey with a real provider and browser observations. Do not enable unrestricted shell or browser tools to fill this gap. Include provider failure and unknown-action-outcome tests.

### 4. Define and verify the worker runtime/bootstrap

The project's manifest requires Node `>=24.13.0`; this review's shell provides Node `v22.17.0`. Existing baseline checks pass on that shell, which does not verify the declared supported runtime. Isolated worktree snapshots exclude `node_modules` and `dist`; existing tests import compiled `dist` files. The plan's direct per-feature test commands need an explicit dependency/build setup.

The host browser runner exists, but `scripts/node_modules/playwright/package.json` is absent. Playwright installed inside u_bot does not automatically satisfy module resolution for a runner under the host's scripts directory. The supplied setup script or a documented isolated runner setup is required. The Python virtual environment has no pytest.

Required correction: select the supported Node runtime; define dependency bootstrap and compilation/import conventions per worker; verify host browser availability; and restore the controller backend test environment. Keep shared manifests/lockfile under their assigned owner, and do not count missing prerequisites as passed checks.

## Scheduling limitation

The plan says ready work may fill free slots. The current scheduler waits for the complete batch before integrating and computing the next batch. UI/data can therefore be ready while slots sit idle. Either implement continuous refill or describe fixed waves accurately. This is a throughput limitation; it does not invalidate the dependency graph.

## Checks performed in this review

| Check | Result |
|---|---|
| u_bot typecheck, lint, production build | Passed |
| u_bot existing core/provider integration suites | Passed: 16 core/HTTP tests and 3 provider tests |
| Appling frontend tests and production build | Passed: 58 tests |
| Appling backend pytest suite | Blocked: `.venv/bin/python: No module named pytest` |
| Plan parse, dependency scheduling and approval-input hashes | Passed |
| Temporary behavioral probes for single-task safeguards and QA separation | Reproduced the gaps above |
| Fresh UI/browser QA or authenticated provider/account/meeting journeys | Not run; no new UI QA pass is claimed |

Existing task-1 evidence includes successful browser-final, release-browser-phi and restart/recovery reports. Earlier failed browser probes are also retained; a failed marker check must not be described as the final passing report. Provider receipts exist from earlier on 18 November; they were inspected, not rerun. All these receipts concern the existing core/provider slice, not the unfinished features.

## Completion boundaries to preserve

Keep the approved scope and P01–P10 design. Browser/account integrations, meetings and demonstration learning remain required. Keep exact-action approval boundaries, local speech and the zero-additional-recurring-spend constraint. Real sign-ins, WhatsApp pairing, speech model/audio setup, meeting admission and individually reviewed external actions remain live acceptance prerequisites.

Five consecutive actual daily briefing runs remain required by the saved requirements. Finishing code or passing simulated-clock tests does not satisfy that requirement.

No application source, approved inputs, controller approvals or live project state was changed during this review. Build outputs were regenerated by the verification commands. This review document is the only authored repository addition.

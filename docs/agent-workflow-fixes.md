# Agent workflow corrections — 18 November 2026

These changes apply to Appling's planning, developer workers and independent QA. They do not rewrite generated applications or grant project approvals.

## Planner and reviewer

New plans use `parallel-v2`. Every task declares development/integration/verification, an explicit supported role, file ownership, requirement IDs, dependency input contracts, concrete outputs and acceptance commands with expected outcomes. An integration task must consume all implementation outputs transitively. Verification tasks use reviewer roles and may own only tests and their evidence.

The response also declares runtime tools/minimum versions, fresh-worktree bootstrap commands and browser prerequisites. Acceptance journeys map requirements to responsible tasks and describe trigger, actual operations, review/resume boundary, observable result and an end-to-end check. The validated JSON is included in the reviewable plan document, so its revision binds the execution contract too.

A separate, source-read-only architecture session reviews the candidate against actual source and approved requirements. Missing contracts, coverage, invalid reviewer roles, or reviewer findings get bounded correction passes; repeated failure pauses planning without replacing the existing plan. A model review is an additional check, not owner approval or a guarantee of completeness.

Planning briefings distinguish the controller-supported role catalogue from the
project's selected team. The latter is a preference, not a restriction on which
roles the scheduler supports. A replacement proposal is not required to match
the saved task ledger: the planner receives that ledger, prior contract,
checkpoint, memory and project brain as explicitly historical context. The
independent reviewer receives one structured candidate (plan, parsed tasks,
runtime and journeys), approved inputs and current source access, without the
old task ledger or old review checkpoint competing as authoritative assignments.
Adoption happens only after validation and independent review; owner approval
still gates execution. The candidate-context session version starts a fresh
planner session without changing existing instructions or execution approvals.

Drafts are saved before independent review, together with accumulated findings
after each rejected review. A continuation resumes that candidate when its
approved inputs and source still match, including after restart; changed source
invalidates reuse. The planner receives all retained reviews and is asked to
preserve resolved corrections. Each new review checks the complete journeys and
prior findings, distinguishing missing plan assignments from acceptance evidence
that must be produced during implementation. There are at most four proposal
attempts per submission; repeating an unchanged candidate and the same findings
stops early. Summary prose alone does not count as progress. No budget exhaustion,
saved draft or saved review can substitute for a passing fresh review and owner
approval. Successful adoption clears the draft.

Planner sessions are versioned by policy. Existing pending plans require `/replan` before approval under the new contract. This preserves approved requirements, prototype and useful source. Old approvals are not silently promoted or rewritten.

## Developer and QA execution

All development tasks use isolated worktrees, including a single foundation, integration or follow-up task. Every task must return passing checks backed by nonempty evidence inside its own directory. Planned acceptance commands must all be represented. File ownership and protected approved inputs are checked before integration. Blocked work is retained for inspection/recovery.

Reviewer roles are honored without silently substituting a developer. Each worker has its own session. Verification source edits invalidate results and cannot be integrated. Final controller QA/security also runs in a fresh isolated snapshot; only newly assigned evidence can reach the main project. This is controller-enforced result protection; it does not claim an operating-system guarantee that a model cannot write inside its disposable workspace.

The scheduler now integrates each validated completion and refills its slot
without waiting for the rest of a fixed wave. It checks dependencies against
durable integrated results, excludes active ownership conflicts, and snapshots
the latest integrated source for new work. Configured capacity changes affect
the next refill. Failed tasks are attempted once per build invocation; unrelated
eligible work can finish while failed branches remain blocked. The displayed
dependency groups illustrate one possible ordering, rather than batch barriers.
Nested native Codex workers remain disabled in managed development.

Stop checks guard worker execution, model invocation and integration; integration
and stop share the controller lock. Prepared, interrupted and completed worktrees
remain recoverable, including a stop after model completion but before apply.
Completed verified results can integrate on resume without another model run.
Worker errors identify the task and the actual blocker or failed command/exit
code. A passing subset retry never makes a failed combined check pass.

Invocation records include requested model/effort, instruction hash, role and worker identity. Codex additionally records resolved model/effort when returned by its app-server; otherwise the record explicitly identifies requested/default configuration.

## Runtime and validation

Read-only preflight checks declared executable versions and the project's explicit Node minimum before starting a worker. Browser-dependent plans check that the host runner can resolve Playwright and its Chromium installation. Bootstrap commands remain visible in the approved contract and are executed by the assigned engine under normal permissions; preflight does not execute arbitrary model-provided setup commands.

`start.sh` uses the existing Python virtual environment for service checks, installs the declared test extras, and uses a checkout-local Node runtime when installed under `.appling_c/runtime/node_modules/node/bin`. Browser setup uses the scripts lockfile and a checkout-local browser/cache directory. These paths are forwarded to engines.

Local prerequisites prepared during this change: Python pytest/pytest-asyncio, checkout-local Node 24.13.0, host Playwright and matching Chromium. No global runtime or generated application's manifest was changed.

Regression tests exercise real temporary projects, retained workspaces, process version probes, independent review failures, missing evidence, unowned writes, source mutation during QA, stale plan rejection and invocation provenance. Browser or live model acceptance is reported separately from these deterministic tests.

## Verification result

- Full backend suite: 125 passed using `.venv/bin/python -m pytest tests -q`.
- Frontend: 58 tests passed; production build passed. No frontend source was changed for these agent corrections.
- Live runtime preflight observed checkout-local Node 24.13.0 and the host Playwright/Chromium installation.
- Appling restarted successfully at `http://127.0.0.1:9213`; the home page returned HTTP 200.
- u_bot phase, tasks, approvals and requirements/prototype/plan hashes were compared before/after restart and are unchanged. It remains at plan review, not running.
- No fresh paid/authenticated model planning run or new browser acceptance campaign was performed. Existing project plans have not been regenerated or approved. The next `/replan` exercises the new planner/reviewer contract with the selected real provider.

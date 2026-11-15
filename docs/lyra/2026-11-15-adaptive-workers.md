# Adaptive parallel workers — Appling v0.17.14 beta

The previous working Codex source is saved and pushed as
`appling-codex-working-before-adaptive-workers-2026-11-15` (`c9e02c279`).
The original Hermes checkout/service remains separate.

## Decisions and limits

The existing delegate_task tool accepts workers, reason and parallel. The model
chooses a useful count based on independent tasks, dependencies, integration and
resource costs. The host enforces capacity and file isolation; it does not claim
to know an optimal count from an unmeasured speed heuristic. Multi-task requests
must explain the split. The selected count, reason and shared capacity appear in
display-only status messages, without rewriting cached model history.

One pool defaults to ten executing workers across projects in the Appling daemon.
Role leads count; the owner-facing coordinator does not. Settings → Parallel work
can select 1–15, with values above ten marked experimental. Lowering a limit does
not interrupt existing work: new slots wait until usage falls below the limit.
A lead using one slot can run nine helpers at the default limit. Excess tasks run
as its reserved workers finish earlier assignments. Finished worker loops release
slots promptly. Nested expansion never waits holding all capacity; it returns the
lead to direct work if no slots are free. Other coordinators can wait cancellably.

## Roles and source safety

All selected role leads can delegate same-role investigation or writing. Independent
selected roles can also run together when the coordinator declares parallel=true.
Those isolated workers are leaves: they cannot create more workers or introduce
unselected roles. Requirements helpers are restricted to read-only investigation;
the owner interview, approvals and final decisions remain with Appling/a role lead.
Dependent role handoffs retain their serial behavior.

Every isolated batch starts from a clean committed Git baseline. Writers must have
explicit disjoint owned_paths. Shared requirements, plans, manifests and progress
remain lead-owned. The existing ownership/intermediate-commit checks and temporary
Git integration remain in force. Independent final QA and combined checks are still
required after integration; a successful merge is not functional acceptance.

Read-only QA/research/review workers receive separate baseline worktrees and native
read-only sandboxes. A source edit rejects the result, preserving the worktree for
inspection. The host checks baseline freshness before accepting read-only results.
Mixed writing/reading waves explicitly require checks to be rerun after integration.
Role leads consolidate full reports saved under .lyra/codex/reports rather than
letting many workers edit one progress file. QA preview hosts use each worker's
workspace; browser sessions, ports and temporary artifacts are independent.
Worktrees are not an OS security boundary; Git validation supplements native sandbox
and approval controls. Workers must not bypass rejected ownership/integration.

Stop signals sibling sessions concurrently, so a slow child cannot delay the Stop
signal reaching the rest. Slot reservations release on completion, cancellation,
validation failure and exceptions. Wave events record duration, observed peak
workers, token usage, outcome and recovery location for future comparisons.

## Validation

- Ten real Codex coding workers completed concurrently in isolated worktrees.
  The host integrated ten owned files in 22.6 seconds; an independent combined
  gate passed 30 arithmetic assertions and verified a clean primary tree.
- This is a tiny smoke workload, not a LaTeX-build speed estimate or proof that
  ten workers are always faster than fewer workers.
- Executable native-protocol peers exercised full 10- and 15-worker QA batches,
  native read-only policy, a lead plus nine helpers under the ten-slot budget,
  mixed selected roles, leaf restrictions, rejected source edits, ownership overlap,
  pool exhaustion without deadlock, concurrent Stop and slot release on failures.
- Real HTTP tests checked invalid limits, saving 15 and persistence across restart.
- The supported Codex regression checks passed 226 backend checks, with nine
  release/version checks also passing. UI tests passed 41 checks
  and the TypeScript/production build passed. Release/version checks are separate.

Run the matrix from the migration notes, adding:

```sh
scripts/run_tests.sh tests/lyra_lite/test_adaptive_workers.py
```

Fifteen-worker concurrency has protocol-peer coverage; the live model smoke used
ten. More browser/build processes can become a local bottleneck, and the planner
should lower the chosen count when measurements show contention or rework.

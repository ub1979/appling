# Adaptive Hermes workflow

The requirements interview, selected providers/models, owner approvals, project
memory/recall and repository ownership contracts remain unchanged. This release
changes execution instructions and handoffs; it adds no model tools, engine,
provider, scheduler, environment flag or dependency.

Role leads decide useful worker counts from ready independent work, context/startup
cost, provider limits and free shared capacity. Ten executing leads plus workers
is the default ceiling, configurable to fifteen. A lead consumes a slot; no fixed
count is required. The initial handoff includes an advisory capacity snapshot,
while the existing reservation guard remains authoritative. Small changes may run
directly. Counts and rationale for dispatched batches are recorded in worker_plan
with both leaf count and total including the lead.

A task's real dependencies and owner gates control its start, not a blanket
phase or wave barrier. Compatible ownership/workspaces are still necessary.
Coding leaves use disjoint declared paths in isolated worktrees; the same lead
integrates the batch and validates the combined result. Independent final QA
uses the committed integrated build. QA leads can distribute same-role checks;
leaves cannot recursively delegate or edit shared source/reports.

Coherent edits and regression cases can be batched with existing tools; one
assertion does not require one model turn or test process. Working code is not
discarded merely because of test-writing order.

Handoffs carry scope, exact paths/contracts, setup/check commands and relevant
Brain references, without copying the whole conversation. Leads update the Brain
once per verified milestone with decisions, commit, checks, blockers and evidence
links. Existing memory and recall code is untouched. Retests cover affected or
invalidated behaviour; broader suites remain required by acceptance or regression
risk. Previously valid evidence is not discarded or relabelled without inspection.

Validation uses real daemon HTTP, Hermes, tools, temporary Git worktrees and
provider-routing paths with scripted local model responses. Cases cover direct
execution, independently chosen batch sizes through the 10/15 limits, coding merges,
read-only QA, selected model/provider inheritance, Stop, approval gates and stable
per-conversation system/tool prefixes. These tests establish runtime behaviour,
not model decision quality or an end-to-end speedup guarantee. Existing live QA
previously demonstrated three concurrent workers; no production app is modified
as part of installing this release.

Rollback source: annotated tag
`appling-hermes-working-before-adaptive-2026-11-16` at `8ed27318f`.
Stop only idle Hermes, restore that source on a branch, and start Hermes again.
Do not reset project repositories, delete .lyra, restore old project data over
new work, or touch the separate Codex checkout. Deployment keeps a private
backup of configuration, registry and per-project state/history before restart.

Live configured-model smoke checks also completed in disposable workspaces:
three independent dependency-free modules and their regression tests, followed
by an independent Node test invocation. The model chose one lead and no workers
for these small tasks, explicitly citing coordination cost. Both passed (10 and
11 tests respectively). One initial temp location triggered the file tools' path
guard; the second run used the designated disposable project area. No guard was
disabled and no existing application was modified. These observations support
adaptive direct execution, not a general performance or quality guarantee.

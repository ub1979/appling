# Five-minute status and isolated development

## Recovery point

The previous working tracked source is commit `837289168`, saved on GitHub as
annotated tag `appling-nice-working-one-2026-11-14`. Its annotation begins
**Nice working one**. The implementation is on the separate branch
`codex/status-and-parallel-development`. The unrelated local chat summary is
not part of either release.

To return to that source, first finish or stop active Appling work, stop the
server, switch the Appling checkout to the tag (or a new branch from it), and
restart. Do not reset generated project repositories or erase their `.lyra`
folders. The source rollback is independent of project work/history.

## Design and boundaries

Status notes are deterministic summaries of existing activity. A daemon tick
appends one display-only transcript note every five minutes while a turn or
agent is active. No new model request, injected user message, toolset change,
prompt rebuild, queue item or model-history edit is involved. Paused/idle
projects and owner questions suppress the timer. Heartbeats do not count as
file/tool progress; a quiet wait is described honestly. Notes survive refresh
and restart through the existing transcript and SSE mechanisms.

Development uses one lead with at most three leaf coding workers. The host
grants two delegation levels only to Appling; the global Hermes default is
unchanged. Non-development phases remain ordinary leaf agents. The lead's
initial task context explains the contract before its first model request.
Existing approval checks run before development is dispatched. The global
orchestrator kill switch and normal concurrency/approval controls still apply.

Workers declare disjoint project-relative paths in JSON task context. The
host checks overlap, including case variants, before creating separate Git
worktrees and indexes from one committed baseline. Shared contracts,
configuration, dependency manifests/lockfiles and Project Brain belong to the
lead. Each worker receives its actual cwd in both tools and its initial prompt.

Integration requires every worker to complete normally. It validates both net
changes and intermediate commits against ownership, commits validated worker
changes, and merges into a temporary worktree first. The primary project is
advanced only when its branch, HEAD and clean working state still match the
baseline. A rejected wave leaves its branches/worktrees/reports under
`.lyra/development/` for serial recovery. Stop propagates to nested workers and
prevents automatic integration. There are no force resets, conflict overwrites
or automatic pushes. Successful checkouts are removed without force; Git
branches and wave reports remain available for recovery.

Worktrees prevent ordinary edit/index collisions; they are not an OS sandbox.
Independent code can still have semantic integration bugs, so the lead must
run combined tests, type checks, builds and relevant browser checks before
claiming completion. Dependency installation stays inside the normal tool and
approval path. Remote terminal backends retain serial development because
host worktrees do not establish their workspace boundary.

## Configuration

```yaml
lyra_lite:
  status_updates:
    enabled: true
    interval_seconds: 300
  parallel_development:
    enabled: true
    max_workers: 3  # bounded at three; also respects Hermes' concurrency cap
```

Settings are scoped to the selected Hermes home. Disabling parallel development
restores ordinary developer leaves for newly built agents. Existing live
agents keep their original schemas and prompts. No active production server
was restarted to introduce these changes.

## Verification

The backend suite exercises existing approvals, update/review recovery,
provider waits, Stop, conversation caching and watchdog behavior. Additional
real Git tests cover separate indexes, overlapping/unsafe ownership, unowned
intermediate commits hidden by a revert, failed/incomplete workers, changed
primary state and merge conflicts. A real daemon and scripted local provider
prove simultaneous nested workers, relative file/terminal cwd routing, leaf
tool restrictions, integration and display-only status without extra requests.
UI tests verify that a status event refreshes history without replacing an
in-flight reply. The browser smoke check showed the note inside the actual
production-built conversation UI on a temporary local instance, with the
composer and project map intact. Test results are recorded in the change's
commit description.


## Follow-up fixes — 2026-11-15 (Appling v0.17.12 beta)

Nested callbacks now relay descendant tool, thinking, progress, spawn and provider
status events with their original identities. Status notes count current nested
workers and returned results, show the latest real tool timestamp, and report
heartbeat liveness separately. A quiet tool clock never implies an AI connection
wait; that wording requires an actual provider status. Returned worker results do
not imply a successful merge or completed app. These remain display-only notes.

Pre-development plan review now records the approved requirements/plan baseline
when development actually starts. Later engineering edits no longer reopen that
same approval at delivery. Recovery uses an answered plan approval followed by a
recorded development start, preserves the original approval hash, and suppresses
recovery of the erroneous late card. A changed plan before execution still needs
review. Update project resets the execution baseline and approvals for its new
cycle. Real daemon tests cover delivery/restart, nested worker events, and update
reset without live model credentials or changes to cached prompt prefixes.

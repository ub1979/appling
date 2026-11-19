# Validation

## Automated coverage

Latest local result: **88 backend tests passed; 58 frontend tests passed;
2 WhatsApp bridge filter tests passed**.
TypeScript checks and the Vite production build passed. The stylesheet was
initially copied from the original interface; the composer now has six visible
lines and grows to ten, as requested. Ordinary questions use normal chat bubbles.

- Backend behavior checks exercise the complete controller flow with temporary
  project files, revision-bound approvals, task dependencies, memory isolation,
  interruption/restart, follow-up changes, API authentication and settings.
- Parallel-development checks use real temporary Git repositories and detached
  worktrees. Barriers establish actual worker overlap, task-scoped session
  isolation, dependency ordering and evidence integration. Checks cover staged
  and unstaged work, unchanged user HEAD/index, excluded secrets, tracked ignored
  source, overlapping ownership, rename/symlink boundaries, escaped evidence,
  cancellation, retained session resume, new task revisions, conflict
  reconciliation and a crash immediately after patch application. Editing a
  retained workspace requires fresh verification before reusing its result.
  Older approved plans can receive read-only execution ownership assessment;
  tests ensure goals/approvals remain intact and invented/cyclic tasks are rejected.
  Two controlled Codex app-server subprocesses also run concurrently through the
  full engine adapter, receive distinct human permission replies, and integrate
  their actual file output through the Git coordinator.
- Phone checks exercise the real controller with temporary state and controlled
  transports: private expiring owner pairing, exact cross-project replies,
  Telegram buttons, stale revisions/duplicates, private credentials, secret
  exclusion, disconnect, WhatsApp self-chat/echo filters, HTTP session auth and
  the Node sidecar's real subprocess protocol. They do not send external messages.
- Interleaved worker usage is counted by invocation rather than the last helper
  that happened to start. The frontend distinguishes project limits from agent
  limits and targets the exact worker question in the shared chat composer.
- Launcher checks cover occupied-port fallback, strict explicit ports, permission
  failures, and keeping the browser URL aligned with the reserved server socket.
- Real subprocess lifecycle checks cover detached startup, reusing an existing
  instance, checkout-local graceful stop, ignoring stale PIDs, and immediate
  reporting when a background child fails to start. These do not bind HTTP ports.
- Connection checks cover live RPC-shaped model catalogues, pagination, Claude
  alias/login distinction, authenticated API model discovery, discovery cache
  refresh, selected-model inference requests, and visible failure messages using
  controlled processes/transports. Frontend rendering checks verify the primary
  dropdown, connection-test controls and quota/context disclosure.
- Claude regressions cover stdin EOF, plain-text and pretty-printed JSON results,
  resolved model reporting, login-error propagation with secret redaction, and
  using the same custom Claude config for authentication and generation.
- Conversation checks cover normal question rendering without a separate input,
  a six-row shared composer, and persistence of multiline answers and questions
  through submission and reopening the project store.
- Subprocess protocol checks exercise Codex initialization, thread resume,
  approvals, questions, task completion and usage notifications through a real
  child process implementing the protocol.
- Claude/Copilot adapter checks exercise structured events, permission gating,
  command flags and process completion through controlled child processes.
- HTTP adapter checks exercise Ollama/OpenAI-format tool calls and actual file
  writes, Anthropic Messages requests, stable session prefixes, interrupted
  exchange recovery and context compression using controlled HTTP transports.
- The preserved frontend's behavior tests, TypeScript checks and Vite production
  build run independently from the original checkout.

## Installed runtime check

The installed Codex CLI (0.164.0) successfully answered an app-server initialize
request using a disposable Codex home. No model call or paid work was requested
by this check. CLI installation is not proof of login or model entitlement.

The installed 0.164 stable protocol schema was also checked for native activity,
permission callback and interruption contracts. An ephemeral read-only thread
accepted the managed-worker dotted feature overrides without starting a turn.
Controlled real child processes test streaming, concurrent human requests,
root/child result separation, permission scope, redacted failures, interruption
and process-group cleanup. These establish protocol behavior, not authenticated
parallel model execution.

## Environment limitations

The backend initialized successfully, but this execution environment denied
binding `127.0.0.1:9210`. Consequently a live browser walkthrough of the new
studio was not performed. Browser automation installation was also unavailable
from the offline package cache; `scripts/setup-browser.sh` provides the normal
installation path.

This change reconfirmed that even temporary localhost socket binding is denied,
so the new Settings and worker views have rendering/type/build validation but
no live browser walkthrough. No running project was restarted or migrated.

Live Telegram pairing, delivery and approvals remain unverified. The optional
WhatsApp bridge pins the verified upstream `baileys@7.0.0-rc14`; npm registry DNS
was unavailable here, preventing installation, a genuine dependency lockfile and
authenticated WhatsApp checks. Run its documented `npm install` setup before
pairing. No dependency lockfile or successful live connection is fabricated.

Authenticated real-model generation through Codex, Claude Code, Copilot, Ollama
and API providers has not been verified here. Protocol and controlled-transport
tests establish integration behavior, not model output quality or a speedup.

The installed Claude CLI was exercised through the corrected one-shot path. It
returned `Not logged in · Please run /login` in this execution session; that
response is now surfaced instead of a generic failure. This does not establish
the login state of a separately launched server or a successful paid inference.

## Live acceptance run

On a machine with localhost access and the selected engine authenticated:

1. Launch with `./start.sh`, choose the engine/model in Settings, and create a
   simple counter application in a disposable project folder.
2. Complete the interview. Open and approve the clickable prototype, then the
   requirements and plan. Confirm implementation did not start before approval.
3. Allow build/test commands, inspect the browser evidence and try the built app.
4. Request an in-scope fix and confirm it reuses approved requirements.
5. Add a materially new feature and confirm it receives a focused requirements
   update. Modify a reviewed artifact and confirm stale approval is rejected.
6. Stop/restart during work, switch the development connection, and confirm task
   checkpoints and earlier user decisions remain available.
7. Repeat with each intended connection before treating it as release-verified.
8. Plan two independent features with separate file ownership and a third
   integration task depending on both. Set development agents to at least 2;
   confirm the first two have distinct simultaneous workers and the integration
   task starts after both are integrated. Repeat with limit 1 and with shared
   ownership to confirm serial operation. Interrupt and resume a parallel wave.
9. Pair Telegram and/or WhatsApp, answer an exact pending worker question, approve
   the offered revision, then verify an old approval and an unpaired account are
   rejected. Disconnect and confirm phone control is revoked.

The first implementation is suitable for these local acceptance checks; it is
not represented as a production-validated release.

## Agent workflow corrections — 18 November 2026

The complete backend suite passes: 125 tests, including new temporary-project
regressions for single-worker isolation/evidence, reviewer session separation,
rejected QA source edits, incomplete plan contracts, independent plan review,
stale-plan approval rejection, runtime preflight and invocation provenance.
The frontend's 58 tests and production build pass. No frontend source was changed
for this correction, and no new UI QA pass is claimed from these automated suites.

Node 24.13.0 and host Playwright/Chromium were prepared locally. The updated
service restarted at http://127.0.0.1:9213 and returned HTTP 200. Existing u_bot
tasks, approvals and approved-input/plan hashes remain unchanged. Real-provider
planning under the new parallel-v2 contract remains to be exercised by the next
owner-requested replan; deterministic test engines do not establish model quality.
See docs/agent-workflow-fixes.md for the revised contract and execution boundaries.

## Replacement-plan briefing correction — 18 November 2026

The u_bot failure exposed conflicting planning inputs: `available_roles` was
populated from its two-role selected team, and the independent reviewer received
the old stored execution tasks alongside the corrected replacement candidate.
It demanded adoption of the candidate before review, although the read-only
planner cannot change controller task assignments.

Briefings now expose supported roles separately from selected roles, label the
planner's old tasks/contracts/memory as historical, and supply the reviewer one
structured candidate without the old ledger, memory or review checkpoint.
Planner sessions rotate for this briefing version. No approval is granted by
this change, and existing execution contracts are not invalidated.

Validation: **127 backend tests passed; 58 frontend tests passed; TypeScript and
the production build passed**. Two new temporary-project regression cases cover
successful replacement review and a reject/correct/review cycle, stale QA
assignments, supported developer/reviewer roles, session rotation/resumption,
unchanged saved tasks during review, preserved input approvals, and the final
revision-bound owner review. Existing rejection tests still verify that genuine
review failures pause without adopting the candidate.

The running server was not restarted: even binding an ephemeral localhost socket
returns `PermissionError: [Errno 1] Operation not permitted` in this session.
The fix is on disk and requires a normal host restart (`./stop.sh` followed by
`./start.sh`), then a planning retry in u_bot. No new authenticated model run or
browser QA pass is claimed for this correction.

## Plan correction recovery — 18 November 2026

Planning now saves the latest candidate before review and retains every rejected
review for the next correction. Continuations restore that draft after restart
when the approved inputs and source match. Source changes invalidate draft
reuse. Reviews audit complete journeys and all accumulated findings, while
distinguishing missing implementation assignments from live acceptance evidence
that belongs to execution. Up to four proposal attempts are allowed; unchanged
contracts with the same findings stop early. Passing a fresh independent review
and obtaining owner approval remain mandatory.

Validation: **131 backend tests passed; 58 frontend tests passed; TypeScript and
the production build passed**. New temporary-project behavior checks cover two
successive corrections without losing earlier findings, restart recovery,
source-change invalidation, unchanged-response termination, retaining a candidate
when review is interrupted, and preserving saved tasks/approval gates. The
recovery changes are on disk; the already running service must load them on its
next normal restart. Live recovery of the current u_bot plan is recorded below
separately from these tests.

### Live u_bot recovery

Continued the retained candidate through the running studio's normal chat
composer, with concrete assignments for the persisted provider-operation loop
and the Mac meeting-audio bridge/early feasibility check. The configured Codex
planner produced 13 tasks and eight acceptance journeys. A fresh independent
architecture invocation returned `verdict: pass`, `findings: []`. The controller
saved the replacement under `parallel-v2` and entered `plan_review`, stopped
running, with a pending review bound to the actual plan revision. Requirements
and prototype approvals still match their files; plan approval remains absent.

The computed waves are contracts; browser/WhatsApp/speech;
productivity/social/workflows; briefings/meetings/data; UI; integration; QA.
Browser evidence confirms the plan opens and the normal “Approve implementation
plan” control is enabled. Evidence: `docs/evidence/u_bot-plan-review.jpg`.
No owner approval was submitted and no development task was started.

This is a passing planning review, not live acceptance of the generated app.
BlackHole was not installed and the reviewer could not verify the Swift
toolchain within its sandbox. The plan retains early audio feasibility and
actual provider/account/meeting/briefing acceptance as execution/release gates.

## Execution lifecycle QA — 18 November 2026

Reproduced the owner's exact Git failure with real `.gitignore` entries and
populated `.appling`, `dist` and `node_modules` directories. Snapshot staging now
enumerates eligible tracked and unignored untracked files, filters generated and
private paths, and stages literal NUL-separated names through the disposable
index. Approved artifacts and assigned evidence are collected explicitly without
passing ignored exclusion pathspecs to Git. This retains tracked ignored source
and ignored evidence without force-adding generated dependencies or secrets.

An actual u_bot snapshot and disposable worktree then succeeded with the original
HEAD and staging index unchanged. Building that workspace exposed a second issue:
macOS `/var` and `/private/var` aliases disagreed during artifact collection.
Canonicalizing the snapshot root fixed it; the actual post-build snapshot passed
and excluded `dist`, `node_modules` and `.appling`. Regression tests cover both
canonical and aliased roots, ignored artifacts/evidence, secret exclusions,
literal filenames and deletion capture. Existing worker lifecycle fixtures now
create ignored dependencies before execution and generated output during worker
execution, so parallel integration, restart/resume, conflicts and independent QA
all exercise this real project layout.

Also fixed the scheduled verification-worker response contract: it now requests
the `verdict` field the controller requires, in addition to status and check
evidence. Controller final QA already requested this field.

Results: **133 backend tests passed; 58 frontend tests passed; TypeScript and the
studio production build passed**. In the disposable actual u_bot workspace,
typecheck, lint and build passed. Core/provider test commands produced 17 passing
checks and two blocked checks: HTTP and Ollama transport tests could not bind
localhost (`listen EPERM`). The combined integration command therefore did not
pass. Fresh `npm ci --offline` failed for uncached dependencies; the normal
install attempt recorded npm registry `ENOTFOUND` failures. Application checks
used the original installed dependencies linked into the disposable workspace;
this does not certify clean installation.

The live studio remains on its previously loaded Python code: u_bot is paused in
build with all 13 tasks pending and all three approved artifact hashes intact.
No live build success or full project completion is claimed. This session cannot
bind localhost to replace the server, so it was left running. The fixes require
loading on the next host restart. Browser QA, authenticated full-model execution,
external accounts, native audio/permissions and clean dependency installation
remain unverified; none were converted into passing results.

## Installed-runtime startup correction — 18 November 2026

The launcher unconditionally ran an editable pip install on every stopped-service
startup. Reproduction stalled in build isolation trying to download setuptools
from PyPI, despite all server dependencies already being installed and the server
import succeeding. Startup now probes the existing server import and installs
dependencies only when that probe fails. Shell-level regression cases exercise
both installed and missing-runtime paths and verify argument forwarding through
the UI build to service startup.

The actual corrected launcher skipped pip, completed the UI build, and reached
the server process. This execution environment then denied localhost binding
(`Cannot open a localhost listener: [Errno 1] Operation not permitted`). This
does not establish a successful running service. Full backend results: **135
passed**; frontend: **58 passed**, TypeScript/production build passed. No new
browser QA pass is claimed. The service remains stopped pending startup from
the normal host environment; saved project files and approvals were not changed.

## Evidence handoff recovery — 18 November 2026

The live rp-contracts worker returned an empty log for successful, silent
`git diff --check`, plus separate command entries where the approved acceptance
contract declared combined commands. The controller correctly refused integration;
the missing piece was automatic handoff correction and explicit receipt guidance.

Worker goals now require exact planned command strings and nonempty receipts
containing the executed command, actual exit status and output (including an
explicit silent-success entry). The controller gives incomplete evidence one
bounded correction attempt in the same retained workspace/session. Missing logs,
missing check lists and missing exact acceptance commands never count as passes.
Failed checks, escaped paths, invalid verifier verdicts and source edits during
independent QA remain blocking. Source immutability is checked after each
verification invocation, including an evidence repair.

**140 backend tests passed; 58 frontend tests and the production build passed.**
New behavioral cases execute real silent subprocess checks, exercise empty logs
and split-command handoffs, verify successful repair/integration and bounded
failure without adoption, and reject reviewer source edits during the retry.

The current service was recovered through its normal composer without restarting
active work: rp-contracts reran the exact approved checks, saved nonempty receipts,
passed 15 contract/16 core/3 provider tests, and was integrated by the controller.
The next wave actually started rp-browser, rp-whatsapp and rp-speech concurrently.
The added automatic-retry implementation is on disk for the next normal service
start; the current live recovery used explicit coordinator guidance. No full-app
delivery or live account/audio acceptance is claimed from this task completion.

## Rolling scheduler and execution recovery — 18 November 2026

Removed the whole-batch wait in the development coordinator. Completed workers
now integrate through one controller immediately; free slots refill with eligible
tasks while slower independent workers continue. New worktrees capture already
integrated prerequisites. Active file ownership, dependency completion, approval
hashes and the current configured agent limit still govern dispatch. The plan's
displayed dependency groups are a preview, not execution barriers.

Blocked tasks are attempted once per build invocation; their dependents remain
pending while unrelated eligible work can continue. Setup failures also cannot
hide other ready tasks. Prepared workspaces survive restart, verified completed
results resume without another model call, and conflict recovery retains earlier
attempts. Explicit continuation guidance remains scoped to retained attempts.
Stop checks cover worker dispatch, model invocation and integration; stop and
integration share the controller lock so no apply can begin after stop returns.

Errors now include the task and its blocker summary or failed command, exit code
and evidence location. A failing combined check is still a failure when a later
subset retry passes; it is no longer mislabeled as an evidence-folder problem.
Missing receipt correction remains bounded and cannot waive actual failures.

**154 backend tests passed; 58 frontend tests, TypeScript and the production build
passed.** Raw final outputs are in
`docs/evidence/rolling-scheduler-backend.txt` and
`docs/evidence/rolling-scheduler-frontend.txt`. Regression tests use real temporary
project files/Git worktrees and event barriers to prove a follower starts with its
prerequisite integrated while a slow worker is still blocked. They also exercise
ownership conflicts, failed branches, capacity changes, stop during refill,
stop at dispatch/apply boundaries, restart before dispatch, completed-result
recovery and exact failed-check reporting. Existing approval, independent QA,
protected source and native app-server process/permission tests also passed.
The suites report the existing Starlette/httpx deprecation and frontend chunk-size
warnings; neither failed validation.

The live studio was inspected through its browser UI. It was still executing
u_bot on the previously loaded code. Contracts and WhatsApp were integrated;
browser/speech/data attempts included retained blockers. The data handoff listed
an exit-1 combined test and a passing targeted retry, which the controller
correctly refused despite its misleading diagnostic. This inspection is not a
browser QA pass for the patched scheduler or delivery of the generated app.

Live replacement is blocked in this execution environment: both a localhost
connection and an ephemeral localhost bind fail with `EPERM`. The running
service was preserved rather than stopped when this environment could not
replace its listener. The patch requires a normal host restart of Appling to
load; the live project, approvals, workspaces and sessions were not rewritten.
Native audio permissions/devices, live account acceptance and full generated-app
completion remain unverified. No passing acceptance was inferred from prose.

## Service shutdown recovery — 18 November 2026

The attempted host restart revealed another concrete lifecycle bug: Uvicorn
waited indefinitely for live event-stream connections before application
shutdown could run. The old process retained its service lease; status/start
mistook that lease for a working service. The observed log ends at
`Waiting for connections to close`; u_bot is paused with its work retained.

Managed service shutdown now limits connection draining to three seconds, then
runs normal application cleanup. Start waits for a matching stopping instance
to release its lease instead of returning its stale URL. Status explicitly
reports shutting down. A timeout gives an actionable event-stream diagnostic.
No stale PID signaling or force-kill behavior was introduced.

**156 backend tests passed; 58 frontend tests and the production build passed.**
`docs/evidence/shutdown-recovery-backend.txt` contains the final backend output.
New tests run real service subprocesses through stop/replacement and exercise
the managed server's actual Uvicorn shutdown against an indefinitely pending
stream, verifying cancellation and lifespan cleanup without a network listener.
An initial test harness omitted Uvicorn's empty listener collection; corrected
before the final passing suite. Existing deprecation/chunk warnings remain.

The already-running old process cannot acquire this patch retroactively. No
studio tab was available in the connected browser inventory to release its
streams, and process inspection is denied in this session. Live recovery and
replacement remain blocked here; close/reload connected Appling pages on the
host, then start the service after the old lease releases. No live startup or
new browser QA pass is claimed.

## Explicit legacy process recovery — 19 November 2026

The old instance remained stuck after repeated host stop/start attempts. Added
`python -m appling.recovery` as an explicit one-time recovery entry point, separate
from ordinary stop requests. It requires the service lease and matching stop
request, checks the ledger read-only for active projects, verifies the recorded
PID's full Python/module/managed command and checkout cwd using host ps/lsof,
and rechecks the instance before sending one SIGINT. It waits for lease release
before calling the normal launcher. It does not delete lock/state files, use
SIGKILL, mark tasks complete, or change approvals. Start/stop timeout diagnostics
now point to this entry point rather than repeating ineffective tab instructions.

161 backend tests passed, plus 58 frontend tests and the production build.
Final backend output is `docs/evidence/legacy-server-recovery-backend.txt`.
Recovery tests exercise a real retained-process lease, interruption, unchanged
project ledger, and refusal for active work, mismatched process, replaced
instance and unmatched stop request. OS identity inspection itself remains
host-dependent. The attempted live recovery failed at `/bin/ps` with EPERM,
before sending any signal or restarting. Host execution of the recovery command
is still required; live recovery success is not claimed.

## Direct coding flow and honest blocked status — 19 November 2026

Appling now defaults new projects to requirements, a clickable prototype with
revision-bound feedback/approval, requirements approval, native engine coding,
then independent QA and selected reviewers in sequence. Prototype approval is
mandatory in both execution modes. Requirements can recommend additional valid
specialists. Direct Codex builds enable native delegation and peer messaging;
the parent owns application-wide implementation/wiring and a resumable session.
Appling retains project memory, permissions, approval gates and source-bound QA.
A separate implementation plan remains optional. Existing projects are not
silently migrated; explicit idle-mode changes checkpoint their old execution
ledger while preserving files, approvals and retained attempts.

Native helper starts/messages/completions are recorded, active helpers appear
in project detail, and lost completion events cannot leave stale workers after
the invocation ends or the server restarts. Known helper roles are displayed
from controller metadata rather than guessed from words in their task goals.
QA, code review, security and accessibility reviews run independently in order;
failed findings return to the saved builder before fresh verification. The CLI
adapter also tolerates process exit between poll and signaling, preserving the
original redacted diagnostic rather than masking it with ProcessLookupError.

The completion banner now requires the controller's delivered state rather than
completed team markers. Current blocked attempts have a persistent banner and
expandable reasons after reload; obsolete attempts and removed tasks do not
pollute a new plan. Blocked worker responses retain their checks and structured
prerequisites without becoming completed work. Optional planned execution now
requires explicit upstream prerequisites for acceptance commands, rejects
self/downstream/unknown prerequisites, and supplies retained handoffs to both
planning and independent review. This validates declared dependencies; the
independent reviewer must still check semantic completeness against actual code.

Final validation: **178 backend tests passed; 68 frontend tests passed;
TypeScript and the production build passed**. Backend output is
`docs/evidence/appling-direct-workflow-backend-final.txt`. Behavioral tests use
real temporary projects, subprocess checks, Git worktrees and controlled native
protocol subprocesses. They cover prototype revision feedback/stale approval,
missing/changed prototype rejection, direct build restart/session reuse, QA
source edits, bounded repair followed by fresh reviewers, native helper
messaging/cleanup, explicit mode switching and preserved legacy execution.
Earlier failing runs are retained separately: a native helper callback argument
collision was corrected, and the phone approval test was updated for the new
default transition to build instead of mandatory planning. The existing
Starlette/httpx and bundle-size warnings remain nonfatal.

Actual browser evidence verifies the updated blocked banner, absence of false
completion, expandable retained errors, and the disabled build-coordination
control with accurate restart guidance on the older running backend. Evidence:
`docs/evidence/appling-blocked-recovery-ui.json` and `.jpg`; no console errors
were observed for that check. This is not a live end-to-end direct build or
live native-delegation acceptance. Controller test fixture receipts are not
product QA receipts.

Loading the new backend is **blocked in this session**: an ephemeral localhost
bind still returns EPERM. The existing listener was preserved. A normal host
restart (`./stop.sh` then `./start.sh`) is needed to load the new default flow
and build-coordination settings. The UI build is already served and verified.
The live u_bot project remains paused on its original plan, with unchanged
requirements/prototype/plan approval hashes, files and retained workers. No
project replanning, worker adoption, driver installation, OS permission change
or live account/meeting action was performed by this Appling change.

## Activity replay and page-local status checks — 19 November 2026

The Studio previously subscribed after the newest event on refresh, leaving its
Activity list empty until new events arrived. It now replays a bounded 2,000-event
window into presentation only. Old approvals, queues, turns and helper ownership
cannot overwrite the current controller state. Activity entries deduplicate and
remain capped at 200; the newest 60 display. Native Codex tool names have readable
labels. This does not fix the older adapter's missing detailed parsing of the
new subAgentActivity payload or establish an exact native agent count.

A page-local project status check runs immediately and every five minutes while
the page remains open, showing its timestamp and controller status. Closing the
page cancels it; late requests cannot update a closed view; failed requests show
unavailability. It uses the existing project API, does not invoke a model or
modify project messages, and is not a background ChatGPT notification job.
Browser throttling, computer sleep and lost connectivity can delay checks.

71 frontend tests and the production build passed. New tests use controlled time
to exercise the five-minute interval, cleanup, offline errors and late replies;
event replay tests preserve live controller state and reject duplicate activity.
Actual browser verification restored 19 recent entries immediately after refresh,
then showed new live activity and a timestamped Working status. Evidence:
docs/evidence/activity-restored.jpg and activity-restored.json. No backend restart
or interruption of the active u_bot coding session was needed. The five-minute
recurrence was verified with controlled-clock tests, not a five-minute browser
observation; automatic messages in this chat have not been scheduled.

## Written five-minute progress messages — 19 November 2026

The controller now starts a server-side publisher for each active turn and stops
it when that turn ends. Every 300 seconds it atomically saves a `progress` message
and a `status_update` event. The existing live UI refreshes the main conversation
without replacing the active streamed response. Updates summarize actual command
exit counts, observed native helper activity, current blockers and pending input.
Model commentary is redacted and explicitly labelled as an unverified report;
quiet work is never presented as proof of progress or acceptance. No models are
called and no controller approvals, task completion or source files are changed.

Behavior tests use temporary stores and controlled time for the 299/300/600-second
boundaries, durable messages after reopen, competing publishers, delayed checks
without a burst, stopped/paused/idle work, new turns, sensitive data exclusion,
and service-wide publisher shutdown on an instance change.

The existing live backend was preserved to avoid interrupting u_bot. An
instance-bound local publisher uses the same transaction and cadence records for
all projects on that service until its next restart; the integrated workflow
publisher takes over when the updated backend loads. This is an application
feature, independent of the open browser and of ChatGPT scheduled notifications.
Actual browser evidence shows u_bot's first saved progress message at 02:00 London:
`docs/evidence/progress-message-restored.jpg`. This verifies a real published and
rendered message; recurrence timing is covered by controlled-clock tests.

All 184 backend tests, the frontend's 71 tests and its production build passed;
the existing Starlette/httpx and bundle-size warnings remain nonfatal. Backend
test output is retained in `docs/evidence/progress-messages-backend.txt`.
At 02:02 London, the existing u_bot Codex task reached its timeout and the
controller paused it with saved work resumable. Progress posting consequently
stopped, as intended. The service publisher remains attached for later work;
restoring notifications does not claim that u_bot passed QA or completed.

## Codex inactivity watchdog — 19 November 2026

Codex task execution now uses an inactivity budget instead of a fixed total
deadline. The default is 1,800 seconds; `idle_timeout` overrides it and the older
`timeout` setting supplies the fallback. Task reasoning, model/tool output,
progress, token usage, compaction and known native helper events renew the timer.
Unknown thread activity, RPC replies and transport keepalives do not renew it.
Concurrent approval/question callbacks suspend expiry until all are answered;
the last answer starts a full new budget. Cancellation still interrupts the root
and live child turns, and timeout cleanup reaps the app-server process group.
Startup RPCs and explicit connection probes retain bounded deadlines. This
change is scoped to Codex; other adapters keep their existing timeout policies.

The installed CLI generated its protocol JSON schemas locally; the event set
matches its reasoning deltas, command output and MCP progress notifications.
Real controlled child-process tests demonstrate work lasting twice its budget
while root/helper events arrive, silence and unrelated traffic timing out,
retained checkpoint files, process reaping, a human answer taking longer than
the idle budget, a bounded active connection probe and invalid timeout rejection.
A controlled clock additionally verifies the 1,800-second boundary and multiple
pending human decisions. Existing native cancellation tests pass unchanged.

The live restart exposed a separate TCP TIME_WAIT issue. Reserved listeners now
use SO_REUSEADDR so an orderly restart can retain the same localhost URL. A real
socket test exchanges data, closes the connection, rebinds the port and confirms
that a second live listener still cannot take it. Final validation: 199 backend
tests, 71 frontend tests and the production build passed. The existing
Starlette/httpx and bundle-size warnings remain nonfatal. Logs:
`docs/evidence/inactivity-timeout-backend.txt` and `inactivity-timeout-frontend.txt`.

The updated managed service is loaded on port 9211, including the built-in
five-minute conversation publisher. A browser resume request was submitted for
u_bot, but native execution is **blocked**, not running: the Codex child exits at
startup with `Operation not permitted` in this restricted execution environment.
A temporary project-local state profile allowed metadata initialization but
thread resume failed with `workspace routing discovery failed`; this profile
was removed and the normal connection configuration retained. No credentials
were copied. A normal host Terminal launch (`./stop.sh && ./start.sh --port 9211`
from this checkout), followed by a resume message in Appling, is needed to retry
with the CLI's usual runtime access. No long real model build beyond thirty
minutes was observed in this validation.

Before/after receipts confirm unchanged saved session IDs, controller approval
hashes and approved requirements/plan/prototype bytes:
`docs/evidence/inactivity-timeout-before.json` and `inactivity-timeout-after.json`.
Actual browser evidence of the current startup blocker:
`docs/evidence/inactivity-timeout-ui.jpg`. This is not u_bot product QA acceptance.

## Live restart follow-up — 19 November 2026

After the owner restarted Appling from their normal Terminal, the service had a
new instance and u_bot remained safely paused. A browser resume request then
successfully continued the saved Codex thread. Fresh model commentary and
successful real commands confirm that the earlier startup permission blocker
was resolved for this service. No additional backend restart or configuration
change was made during this check.

The exact project Codex journal records successful native `spawn_agent` calls
for `pairing` and `workflow_files`, followed by messages to both. Retained helper
receipts show initial failing checks followed by passing pairing and workflow
file-binding checks. The lead's latest native-isolation check also exited zero.
These observations show useful parallel work and actual peer communication;
they do not establish full integration or independent QA acceptance.

Observation continued through the first real five-minute message, without
forcing its timestamp or invoking the publisher manually. The message was saved
and rendered automatically while the build remained active: 12 completed root
commands, 3 nonzero exits, native activity and an explicitly unverified model
report. No new controller problem or pending owner input was observed. Approved
artifact bytes, controller approvals and the saved Codex session were preserved.

Evidence: `docs/evidence/u_bot-restart-monitor-20261119.json`,
`docs/evidence/u_bot-restart-check-20261119.json` and the actual browser screenshot
`docs/evidence/u_bot-restart-live-progress-20261119.jpg`. Monitoring ended after
this live check; the server-side five-minute publisher continues while work runs.

## Direct workflow continuation and expected waiting — 19 November 2026

The direct builder previously raised RuntimeError for every blocked handoff,
including mixed unfinished code, owner setup and live-acceptance blockers. The
drain treated that as an engine failure and paused the entire project. Direct
mode now validates structured blocker kinds and continues implementation in the
same native session. Setup and live checks remain blocked without preventing
independent coding. There are at most three continuations in an owner turn; a
repeated attempt with unchanged source stops earlier. The counter is retained
in project state. Neither changing summaries nor adding evidence-only files
counts as source progress.

A typed expected waiting outcome is persisted as project attention and a
`work_waiting` event, with a blocked turn-end status and no `problem` event or
RuntimeError prefix. The UI renders waiting/continuation activity. Specific
blockers and worker handoffs remain visible. Owner messages clear the waiting
explanation before resuming. Missing blockers, invalid handoffs, real engine
errors, evidence failures and changed approvals remain guarded. A completed
model response with blockers cannot advance to QA or delivery. Stop prevents
continuation. The existing prototype-first approvals and independent review
pipeline are retained; planned-mode behavior is unchanged.

Regression tests exercise temporary project files, real check subprocesses,
mixed blockers continuing into independent QA, owner-only waits, misleading
completed status with blockers, no-progress detection, bounded progress, durable
attention after store reopen, Stop, retained approvals and genuine engine errors.
Browser verification uses a separate disposable controller fixture with a fake
engine, not u_bot product QA. It shows the setup/live waiting explanation without
a crash banner. Evidence: `docs/evidence/workflow-waiting-browser.json` and `.jpg`.
The fixture tab and server were closed after verification.

Final validation passed 206 backend tests, 72 frontend tests and the production
build, including completion-with-blockers and Stop regressions.
Final logs: `docs/evidence/workflow-continuation-backend.txt` and
`workflow-continuation-frontend.txt`. Existing Starlette/httpx and bundle warnings
remain nonfatal.

The owner-launched service on port 9211 is still running the earlier loaded
Python modules. u_bot was checked before the edits and remained actively building
with fresh successful commands and native activity; no restart, Stop, sign-in,
permission change or model change was performed. The new backend must be loaded
on the next normal host restart, after retaining/checkpointing current work.
Restarting it from this restricted session previously prevented Codex startup,
so that known failure was not repeated. A normal Terminal restart from this
checkout uses `./stop.sh && ./start.sh --port 9211`. After restart, send a resume
message in Appling. Live verification of the new continuation policy on the
actual u_bot build remains pending that activation.
The final live check still showed active, unpaused coding with a fresh command;
its receipt is `docs/evidence/workflow-fix-live-status.json`.

Activation follow-up: the owner restarted from their normal Terminal, producing
service instance `06fb8bac41864d0e93240ac736776b20`. At 14:28 London a browser
resume request continued the saved Codex thread. Its initial context compaction
finished and fresh commands completed, including a zero exit at 14:31. A short
computer-connection interruption did not stop the managed build; reconnection
confirmed running/unpaused state and fresh browser activity at 14:32. No duplicate
resume request or extra restart was issued on reconnection. Evidence:
`docs/evidence/u_bot-workflow-fix-activated.json` and
`docs/evidence/u_bot-reconnected-running.jpg`. The new backend is loaded; actual
automatic continuation on a future blocked handoff remains to be observed in
this live run. This does not establish u_bot QA or release acceptance.

## Acceptance authority, partial QA and checkpoints — 19 November 2026

Three separate proofs; none substitutes for another.

1. **Controller proof (deterministic, fake engine, real temp projects).**
   `python -m pytest tests`: 225 passed (17 new in `tests/test_acceptance.py`, a
   new Codex `subAgentActivity` test, a launcher diagnostic test). Covered:
   criteria are part of the requirements approval hash; a builder-only owner
   label cannot defer; missing implementation behind a live criterion is failed
   and repaired; owner-only remaining criteria end `implementation_verified`;
   setup done runs verification only and delivers only on passing live evidence;
   a failing live check returns to build; a source change makes results not run;
   the no-progress guard skips a third identical builder attempt while recorded
   setup permits a retry; `/criteria` writes criteria and requires re-approval
   without touching requirements.md; checkpoints keep owner-staged entries, skip
   `.env`, databases, ignored files, `node_modules` and out-of-project symlinks,
   and use `refs/appling/checkpoints/<name>` on a detached HEAD. Also covered:
   live criteria need criterion-level reports; omitted exit codes and evidence
   outside the current verification folder do not pass; a live pass claimed
   before setup is recorded stays pending; a failed live attempt tied to a
   waiting criterion still reaches QA while an unlinked failing check is
   implementation work; progress is compared by check outcomes, source,
   criteria and setup (receipts with timestamps no longer defeat the guard);
   builder handoffs are committed to the project branch (`.sdlc/evidence/`
   excluded, handoffs included).
   UI: `npm test` 76 passed (4 new for the acceptance view); `npm run build` passed.
2. **Interface proof (browser).** A separate demo home seeded through the fake
   engine showed the Acceptance panel ("Implementation verified; live acceptance
   pending … Not delivered yet"), the setup checklist and per-criterion table.
   Ticking the setup item recorded it and started a verification-only turn: the
   event log shows only `qa-engineer` was invoked; it then failed because the demo
   used a stopped Ollama connection (intended, to avoid spending model quota).
   Evidence: `docs/evidence/acceptance-walkthrough/01-implementation-verified.jpg`,
   `02-setup-marked-done.jpg`. Long status messages render on one line in the chat.
3. **Real-model proof (Codex CLI 0.164.0).** One direct-mode run asked Codex to
   delegate a file write to a sub-agent. Codex reported the child only through
   `subAgentActivity` items (plus a `wait` collab call without receivers), which
   the previous adapter ignored. Appling now recorded helper start/complete for
   `codex:<thread>` labelled with the protocol's agent path
   (`/root/create_hello`); the file contained `hi`. Evidence:
   `docs/evidence/acceptance-walkthrough/03-real-codex-subagent.json`.
   A full real end-to-end project build with live acceptance was not run.

u_bot checkpoint `dc94d0a` (made before these changes) was tested as it stands:
`npm run typecheck`/`build` exit 2 on one TS2741 error in
`src/accounts/browser-adapters/destination-store.ts`; node tests 218 of 255 pass.
Two browser test files stopped producing output for 30 minutes and were killed;
the failures listed ran and failed (they have durations), causes not investigated.
The build failed and some tests import `dist/`, so some passes reflect stale output. Receipts: `u_bot/.sdlc/evidence/checkpoint-dc94d0a…/summary.json`.
u_bot has no approved acceptance criteria yet, so its live requirements cannot
wait on setup until `/criteria` is run and the owner re-approves. The requirements and QA skills changed (new sessions
for those roles, by design). The developer skill was left unchanged so u_bot's
saved builder session key (`sw-developer:ca186d142f9c4778:direct-build-v1`) still
matches. Its first resume will commit untracked `.sdlc/handoffs/` (about 60 KB)
as a checkpoint; `.sdlc/evidence/` (about 4 MB) is excluded.


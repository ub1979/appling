# appling_c

A fresh, independent Appling implementation with the existing React interface,
visual style and project setup experience. It uses a new Python backend and
interchangeable execution adapters; Hermes is not a dependency.

## Run

Prerequisites: Python 3.11+, Git, and a Node version supported by Vite 8
(Node 22.12+ recommended). Install and sign into the CLI connections you want
to use, or run Ollama locally.

```bash
./start.sh
```

The launcher creates its own Python environment, installs dependencies, builds
the interface and opens **http://127.0.0.1:9210**, or the next available port if
9210 is occupied. The actual URL is printed in the terminal and opened in the
browser. Appling runs in the background and returns your terminal prompt after
startup. Other applications keep running. Starting it again reopens the existing
instance instead of launching another copy.

```bash
./status.sh    # Show the running URL
./stop.sh      # Gracefully stop this checkout's background server
```

Logs are saved in `.appling_c/run/server.log`. For foreground debugging, use
`./start.sh --foreground` and stop that foreground process with Ctrl+C. If an
older foreground copy is already running, stop it with Ctrl+C once before using
the new background launcher.

```bash
./start.sh --no-open --port 9211
```

An explicit `--port` is used exactly as requested; if occupied, the launcher
reports that clearly instead of silently changing it.

### Windows

Appling runs natively on Windows; WSL is not needed. This support is new and
has been tested only on macOS so far, so report anything that fails on Windows.
Install Python 3.11+
(tick "Add python.exe to PATH"), Git and Node.js 22+, then install Codex and
sign in from a normal Windows terminal:

```bat
npm install -g @openai/codex
codex login
```

From the Appling folder, in Command Prompt type `start.bat`; in PowerShell type
`.\start.bat` (plain `start` is a built-in command there). `status.bat` and
`stop.bat` do what the `.sh` scripts do, and `scripts\setup-browser.bat`
installs the browser used for QA. The first start creates `.venv`, installs
Appling and builds the interface, exactly like `./start.sh`.

Differences from Linux and macOS:
- Each program Appling starts runs in a Windows job. Stopping a task ends the
  program and everything it started at once; Windows has no polite stop for
  programs without a window. If Appling itself is force-quit, Windows ends
  those programs too, so there is no leftover cleanup at the next start.
- Commands a builder runs go through `cmd.exe`, so the app's own scripts must
  work there (`npm test` does; `ls` and `rm -rf` do not).
- Programs installed by npm (`codex`, `copilot`, `claude`) are started through
  Node directly rather than through their `.cmd` wrapper, so prompts with
  quotes or `&` reach them unchanged. Windows limits a command line to 32,767
  characters; Codex is not affected because it receives prompts over a pipe,
  but Copilot and Claude receive the prompt on the command line.
- `python -m appling.recovery` is Linux and macOS only. On Windows, end a stuck
  server in Task Manager and run `start.bat` again.

A folder that was used from WSL first holds Linux builds: delete `.venv`,
`ui\node_modules` and `.appling_c\runtime` before the first Windows start.
Sign-ins made inside WSL do not carry over to Windows.

Open Settings to select a default connection/model or assign a connection to an
individual role. `default` selects a CLI's configured model. The dropdown queries
Codex's model catalogue, Copilot's ACP model list, and API `/models` endpoints
(including Ollama). Claude Code displays documented versioned model IDs (including
Sonnet and Opus 4.6), CLI aliases and login status. This list is not an
account-entitlement catalogue; test a selected model to confirm access. API
and CLI connections also accept custom model IDs. Engine
model compatibility and account entitlement still apply.

Use **Refresh list** to refresh discovery. Errors and missing logins appear next
to the chosen connection rather than hiding the model list. Discovery is cached
briefly and does not make inference calls.

Use **Test connection** beside the selected model, an individual role, or in
AI connections. Testing sends a short prompt using that connection's quota and
reports success/failure and latency; no generated project files are included.
Save edited connection settings before testing them. CLI installation alone does
not establish that authentication or a selected model works.

Claude tests use a headless one-shot request with stdin closed and tools disabled.
They accept normal text replies and show the actual resolved model when the CLI
reports it. CLI errors are redacted and displayed directly. If the test reports
that Claude is not logged in, run `claude auth login` in the same account that
starts Appling, then refresh the model list and test again. Existing
`CLAUDE_CONFIG_DIR` and Anthropic CLI endpoint/model environment settings are
preserved for both the login check and generation.

API keys are read from environment variables named in Settings. CLI adapters
use their own login. Appling never silently falls back to another provider.

| Connection | Execution |
|---|---|
| Codex CLI | Direct app-server protocol, saved threads, approvals, interruption and token usage |
| Claude Code CLI | Structured print mode, saved sessions, explicit task permission for edits/commands |
| Copilot CLI | JSONL prompt mode and explicit task permission for edits/commands |
| Ollama | Local OpenAI-compatible endpoint and Appling's tool loop |
| OpenAI / OpenRouter / compatible APIs | Configurable endpoint, model and key environment variable |
| Anthropic API | Native Messages API with tool results |

CLI permissions differ. Codex uses its workspace sandbox and operation approval
requests. Claude Code and Copilot prompt-mode tasks use the CLI's permissions;
Appling asks before granting their edit/shell tools. API-model file tools are
workspace bounded, and shell commands need explicit approval. A shell command
runs with the local user's permissions; it is not an OS sandbox.

## Build workflow

Ordinary questions appear in the conversation and are answered in the main chat
composer. It starts with six visible lines and expands to ten before scrolling.
Use Shift+Enter for line breaks and Enter to send. Failed sends keep your draft.
Prototype, plan, permission and secret controls retain their dedicated treatment.

1. Requirements interviews ask one focused question at a time. Skip, decide for
   me and smart defaults remain available. Answers are saved separately from
   engine sessions, so switching connections doesn't discard them.
2. The designer builds a clickable prototype using realistic sample data.
3. The user reviews the exact prototype revision and the requirements draft.
4. By default, the approved requirements and prototype go directly to the coding
   engine. Its saved builder session owns implementation and integration. Codex
   can call native independent specialists and exchange messages/results; compact
   handoffs under `.sdlc/handoffs/` preserve decisions across restart. Appling
   records native helper activity without creating a competing coding task graph.
5. Requirements may recommend additional specialists. The prototype is always
   created and reviewed, including any requested revisions, before coding starts.
   A separate implementation plan is optional: select **Plan before building**,
   add Task planning at setup, or use `/replan` to request that workflow explicitly.
6. Requirements carry approved acceptance criteria and owner prerequisites
   (`.sdlc/acceptance.json`), each tagged release 1 or later and live or local.
   They are part of the requirements approval; `/criteria` proposes them for an
   existing project and asks for re-approval. Before coding, Appling lists the
   setup you will need to provide.
7. Independent QA checks every release-1 criterion against the current source and
   records passed, failed, waiting on you, or not verified. Only an approved live
   criterion whose recorded prerequisite is not ready may wait, and only after QA
   confirms its implementation exists and its local behaviour passes; a builder's
   "owner setup" label alone never defers anything. Missing code is a failure.
   When only such live checks remain, the project is **Implementation verified;
   live acceptance pending**, not delivered. Marking setup done in the Acceptance
   panel reruns verification only (never the builder); delivery needs passing live
   evidence. Source changes turn earlier results into "not verified". Security runs
   when selected. Findings return to a bounded repair loop; blocked checks never
   count as passes. QA cannot change source and retain a passing verdict.
   Appling commits a milestone checkpoint to the project branch after each
   validated builder handoff and before each resume, skipping secrets and
   generated files and leaving your staged changes alone. Repeated resumes with no
   change in source, evidence, criteria or recorded setup pause with an explanation.
8. Follow-up requests are classified as explanations, in-scope fixes or material
   scope changes. Only new scope restarts the relevant requirements work.

The controller enforces revision-bound approvals. Specialist skills guide work;
they cannot advance workflow gates. Independent tasks can now run concurrently
inside a project; architecture, documentation, deployment preparation and other
selected roles can receive planned tasks. Remote publishing remains a separately
authorized action.

## Parallel development and Codex

New projects use direct engine coordination. In **Settings → This project → Build
coordination**, an idle existing project can explicitly switch between direct
and separately planned execution. Files, approvals and retained attempts are
preserved; the previous task ledger is checkpointed. Existing projects are not
silently migrated, resumed or marked complete. Native coding helpers use the
engine's own agent configuration and limits; Appling's role model overrides
apply to the stages it invokes separately. Independent QA runs after the builder,
followed by selected code, security and accessibility reviewers one at a time.
Reviewer findings return to the saved builder for bounded repairs, then fresh QA.

The following host task scheduler applies to the optional planned workflow.

Settings separates **concurrent projects** (default 3, maximum 8) from
**development agents per project** (default 3, maximum 6). New app plans require
capacity for at least 2 agents and at least one executable parallel wave. Shared
foundations, integration and small follow-up fixes may run alone. The limit
remains a ceiling; it does not require filling every slot. Reducing capacity to
1 pauses plans created under this policy rather than silently serializing them.

Every worker package must be an entry in the structured task list; describing
helpers only in prose does not schedule them. A bounded correction pass rejects
missing ownership and graphs that the real scheduler would execute entirely
serially. Invalid plans pause before approval or implementation. The planner
reuses approved requirements/design and existing code instead of redesigning the
app. Existing approved plans are not rewritten automatically; request a revised
implementation plan to adopt this policy.

To replan an existing project, stop that project's work and wait for the worker
to finish, then send `/replan` with any implementation guidance in project chat.
Appling preserves requirements/prototype approvals, current source and the prior
task ledger, invalidates only the implementation-plan approval, and presents
the new parallel plan for review. Changed requirements or prototype bytes still
need their own approval; `/replan` cannot bypass those gates.

The proposed reusable-block catalogue is described in
[docs/reusable-blocks.md](docs/reusable-blocks.md). The catalogue itself is not
implemented by this execution/planner patch.

The planner describes task dependencies and file ownership. Tasks with disjoint
ownership and satisfied dependencies run in a bounded parallel pool, each in its
own detached Git worktree with its own model session, checkpoint and evidence
directory. The coordinator integrates each validated result immediately and
refills the free slot from the latest integrated source, without waiting for
slower independent workers. Active ownership and the current configured agent
limit still constrain dispatch. A failed task is not automatically rescheduled;
its dependents wait while other eligible work continues. Shared contracts and
overlapping or unscoped work run sequentially.
For older approved plans, a read-only assessment can assign execution ownership
and add necessary dependencies to unfinished tasks. It cannot rewrite goals,
remove dependencies, invent tasks or edit the approved plan. Uncertain ownership
stays serial; the assessment is saved rather than repeated every turn.

Private snapshots include uncommitted application work without committing or
changing the user's branch, HEAD or staging index. Credentials and generated
dependencies are excluded. The coordinator checks ownership, approved artifacts,
passing worker evidence and current project bytes before integrating changes.
Renames, symlinks and newer user edits cannot silently bypass those checks.
Independent QA checks the combined app after development, with security review
when selected; parallel worker results alone never count as delivery.

Interrupted workers retain their workspace and task-specific session. Integration
is journaled so restart after an applied patch can finish without rerunning a
completed worker. Conflicts pause work; a subsequent continuation starts a fresh
workspace from current source and gives the worker the retained attempt's diff
to reconcile. Previous attempts remain inspectable under the private studio
state folder. Editing a retained worktree invalidates its old verification.

Codex workers use the native bidirectional app-server protocol, workspace
sandbox, saved threads, streaming activity, approval/permission callbacks,
compaction notifications and interruption. Managed parallel workers disable
recursive native agents so the host's limits, file ownership and cancellation
remain enforceable: the swarm consists of **separate controlled Codex threads**,
not untracked nested editors. Other Codex calls retain the user's native agent
configuration, and native child activity is reported when present. Unsupported
client requests are denied, rather than silently granting access.

Other adapters use the same task controller with their own supported execution
mechanisms and permission limits. Parallel work can improve elapsed time for
independent tasks, but uses more simultaneous account/model capacity; a speed or
quality improvement has not yet been measured on real app projects.

## Questions and approvals on your phone

Open **Settings → Questions and approvals on your phone**. Telegram and WhatsApp
are opt-in and can be enabled independently. The computer must remain awake,
online and running Appling. No public inbound port or tunnel is created.

For Telegram, create a dedicated bot with [BotFather](https://t.me/BotFather).
Save its token in Settings (a private owner-only credential file), or supply
`TELEGRAM_BOT_TOKEN` to the process that starts Appling. Choose **Pair phone**
and send the displayed one-time code to your bot from your private account.
Use **Send test message** after pairing.

For WhatsApp, install the optional bridge once:

```bash
cd bridge/whatsapp
npm install
```

Then choose **WhatsApp → Pair phone**, scan its QR through WhatsApp's Linked
devices, and send the displayed pairing code in **Message yourself**. Both steps
are required. This uses the upstream, unofficial Baileys library; live WhatsApp
compatibility and account pairing still need verification. See the
[bridge guide](bridge/whatsapp/README.md) for dependency and connection details.

Questions and requirements/plan reviews arrive with the project name and request
code. Reply to the exact message or use `/reply CODE your answer`. Telegram also
offers buttons. WhatsApp supports `/approve CODE` and `/deny CODE your feedback`.
The existing controller rejects closed, duplicated or stale approvals. Only the
paired owner can respond; WhatsApp contacts/groups and secret prompts are not
forwarded into this flow. Responses appear in the original project conversation.

Prototype previews remain local; phone messaging does not make the clickable
preview remotely accessible. Review the prototype in Appling before approving.
Use **Disconnect** in Settings to revoke phone access. Live phone setup has not
been verified in this restricted execution environment.

When updating a running installation, let the current job finish before running
`./stop.sh` then `./start.sh`; refresh the browser afterward. The running Python
process uses its already loaded controller until restarted.

## Browser QA and previews

Install the supplied browser runner once:

```bash
bash scripts/setup-browser.sh
```

This installs Playwright and Chromium. The QA agent receives the runner path,
can write explicit journey checks and run them against the real application:

```bash
node scripts/browser-check.mjs --url http://127.0.0.1:5173 \
  --spec checks.json --out .sdlc/evidence/browser
```

The runner records actions, assertions, screenshots, console errors and failed
requests. A missing browser/environment blocks browser QA. Native mobile and
desktop verification additionally require their own emulator/device tooling;
browser screenshots do not certify native behavior. Expo projects can open a
phone preview through Expo Go once their dependencies are installed.

Generated web pages run on a separate localhost origin with a preview access
cookie. The studio API requires a session token and rejects cross-origin
requests. The visual element picker and responsive preview are preserved.

## Project memory and recovery

Studio settings, task state, approvals, conversations, checkpoints and searchable
memory live in a transactional SQLite database under `.appling_c/`. Each record
and search is scoped to its project. Project files retain human-readable
`requirements.md`, `plan.md`, `.sdlc/project-brain.md` and evidence reports.

Workers receive a bounded task briefing, approved requirements, current tasks,
saved interview answers, relevant memory and their last checkpoint. Source
references are indexed incrementally; deleted code references are removed.
Reading current code remains mandatory before relying on a saved claim.

Instructions and tools stay stable within sessions. Connection or instruction
changes create a new session with a project handoff. API context recovery
preserves the earlier transcript and opens a new session with the current task
and recent actions. Native Codex compaction remains engine-owned. Cache usage is
reported when the provider supplies it; hits and cost savings are not guaranteed.

Restarting pauses interrupted work. Nothing automatically replays privileged
operations. Send a message to resume after inspecting saved progress. Start a
new conversation to replace engine sessions while retaining project knowledge.

While a turn is running, Appling writes a progress message in the project
conversation every five minutes. The server saves these even when the page is
closed. Updates summarize observed command results, helper activity and waiting
input, with model reports explicitly labelled as unverified. Quiet periods are
reported honestly. Updates stop while paused or idle, do not change approvals,
and never mark work complete. Cadence is persisted to prevent duplicate messages;
computer sleep or a stopped service can delay updates without a backlog burst.

Codex builds have no fixed total-duration cutoff. By default, 30 minutes without
task activity pauses the job with a resumable inactivity message. Reasoning,
model output, command output, tool progress and known helper activity renew that
budget; unrelated traffic and the five-minute Appling messages do not. Waiting
for your approval or answer suspends the inactivity timer. Stop remains available.
The Codex connection's `idle_timeout` sets this budget in seconds; its older
`timeout` value is used when `idle_timeout` is absent. Setup RPCs and explicit
connection checks retain bounded deadlines. Other execution adapters retain
their own timeout policies.

In direct mode, a builder handoff with unfinished `implementation` blockers gets
an automatic continuation in its saved native session, even when setup or live
acceptance is also pending. Appling allows at most three continuations per owner
turn, and stops earlier if a repeated attempt changes no source. It retains all
handoffs and reports a normal waiting state with specific blockers. Setup-only
and live-acceptance-only blockers wait immediately. These waits do not appear as
engine crashes and never advance QA or delivery. Stop and all approval gates
remain effective; a new owner message resumes retained work. Actual connection,
protocol, approval-integrity and evidence failures still report errors.

## Development and verification

```bash
python -m venv .venv
.venv/bin/python -m pip install -e '.[test]'
.venv/bin/python -m pytest tests
cd ui
npm ci
npm test
npm run build
```

See [VALIDATION.md](VALIDATION.md) for what was verified and what remains a live
integration check. See [THIRD_PARTY_NOTICES.md](THIRD_PARTY_NOTICES.md) for reused
interface, skill and asset provenance.

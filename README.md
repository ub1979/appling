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
browser. Other applications keep running. Stop this server with Ctrl+C.

```bash
./start.sh --no-open --port 9211
```

An explicit `--port` is used exactly as requested; if occupied, the launcher
reports that clearly instead of silently changing it.

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
4. The planner creates a readable plan plus a dependency-checked task list.
5. After plan approval, the builder executes bounded tasks, resuming saved work.
6. Independent QA checks the integrated app and saves evidence mapped to approved
   requirement IDs; missing coverage blocks delivery. Security runs
   when selected. Findings return to a bounded repair loop; blocked checks never
   count as passes. QA cannot change source and retain a passing verdict.
7. Follow-up requests are classified as explanations, in-scope fixes or material
   scope changes. Only new scope restarts the relevant requirements work.

The controller enforces revision-bound approvals. Specialist skills guide work;
they cannot advance workflow gates. Tasks run serially inside a project, while
independent projects can run concurrently. The concurrency setting does not
promise a swarm of workers inside one project. Architecture, documentation,
deployment preparation and other selected roles can receive planned tasks.
Remote publishing remains a separately authorized action.

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

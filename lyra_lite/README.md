# Lyra Lite

A small, file-first shell around the Hermes engine. Start it with
`./start.sh` (opens <http://127.0.0.1:9200/>) and stop it with `./stop.sh`.
The classic Studio in this folder is `./start-studio.sh` / `./stop-studio.sh`.

- **No hidden terminal.** `lyrad` (`python -m lyra_lite`) runs the engine
  directly. The browser sends messages over HTTP and follows a live feed.
- **Files are the truth.** Each project keeps `.lyra/`:
  - `events.jsonl` holds the activity and is append-only.
  - `messages.jsonl` holds the conversation.
  - `inbox/` holds approvals and questions.
  - `state.json` holds the queue and status.

  A refresh, sleep or restart loses nothing.
- **Helpers** run in the background. Each one's report comes back as a new
  turn, and helpers cut off by a restart are still reported, with the outcome
  marked unknown. **Stop** stops Lyra and its helpers and pauses the project;
  your next message resumes it, with any held reports attached.
- **Keep going:** when the plan still has an unfinished step, nothing is
  running, and nothing waits for the owner, Lyra nudges itself after 10 quiet
  minutes. It is limited to 8 nudges a day, and it gives up after 2 nudges
  that change nothing. Switch it per project in the header. Settings live
  under `lyra_lite.watchdog` in `config.yaml` (`enabled`, `idle_minutes`,
  `daily_cap`, `max_no_progress`).
- **Rules notice:** when `rules/lyra.md` or the app-it playbook changes, open
  chats offer "Use the new rules".
- **Lighter Lyra:** Lyra coordinates and has no shell. Agents build, test and
  commit. Her tool output is capped and her chat is summarised at about 100k
  tokens (`lyra_lite/coordinator.py`).
- **Build profile** (Personal / Reusable / Production) is chosen at set-up and
  scales the plan, the team and QA. A Personal app gets a one-page plan of 1–3
  tasks and one focused QA pass.
- **Project memory, per project only:** a focus note from the project files
  rides along with Lyra's messages; `project_recall` searches the project's
  whole chat, documents, reports and Git history (`.lyra/memory.db`);
  Hermes' shared cross-project memory is not used. "About me" in AI settings
  is the only thing carried between projects.
- **Project Brain:** `.sdlc/project-brain.md`, at most 16 KB, is kept by the
  agents and handed to each agent instead of the whole project.
- **The project map** is read straight from `.sdlc/progress.md` (the phase
  ledger the builder skills keep), so it can't disagree with the files.
- **Hermes runs every project** using the same provider setup as the Studio.
  Choose a linked model and effort with the ⚙ button.
- **Former Claude Code projects migrate automatically** on opening. Project
  files, progress ledgers, chat IDs and conversation history are preserved.
  Original state is backed up in `.lyra/migrations/claude-to-hermes/state.json`;
  retired global settings are backed up under
  `~/.hermes/lyra-lite/migrations/claude-to-hermes/config.yaml` (profile-aware).
  These private backups may contain credentials; do not share them.
  Old approvals expire on restart. Migrated projects remain paused until the
  next owner message, which resumes Hermes with any held reports. Stop the
  previous Appling process before updating; live agents cannot transfer between
  processes. Hermes model providers, skills and review gates are unchanged.
- **Compare runs** with `python -m lyra_lite.report <project> [<project>…]`.
  See `HOW-TO-TEST.md`.
- **Every turn is saved** to the project's Git with the same checkpoint the
  helpers use. Risky commands always wait in the inbox and are never
  auto-approved.

Tests:
- `scripts/run_tests.sh tests/lyra_lite` runs the real daemon, the real
  engine and a fake model server.
- `cd lyra_lite/ui && npm test` runs the UI tests.

# Lyra Lite

A small, file-first shell around Lyra's agent engines. Start it with
`./lyra.sh` (opens <http://127.0.0.1:9200/>).

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
- **Project Brain:** `.sdlc/project-brain.md`, at most 16 KB, is kept by the
  agents and handed to each agent instead of the whole project.
- **The project map** is read straight from `.sdlc/progress.md` (the phase
  ledger the builder skills keep), so it can't disagree with the files.
- **Engines plug in** through `lyra_lite/engines/base.py`. Pick one per project
  with the ⚙ button:
  - `HermesEngine` uses the same provider set-up as the Studio, so every linked
    subscription works.
  - `ClaudeEngine` runs the Claude Agent SDK (Claude Code). It needs
    `pip install '.[lyra-claude]'`, plus an `ANTHROPIC_API_KEY` or an
    Anthropic-compatible address such as Ollama.
    - It has its own config folder, so it never uses a claude.ai login.
    - Hermes' danger check guards its shell commands.
    - It runs agents in the foreground.
    - Its cron, scheduling and worktree tools are switched off.
  - Switching engines keeps the chat.
- **Compare runs** with `python -m lyra_lite.report <project> [<project>…]`.
  See `HOW-TO-TEST.md`.
- **Every turn is saved** to the project's Git with the same checkpoint the
  helpers use. Risky commands always wait in the inbox and are never
  auto-approved.

Tests:
- `scripts/run_tests.sh tests/lyra_lite` runs the real daemon, the real
  engine and a fake model server.
- `cd lyra_lite/ui && npm test` runs the UI tests.

Plan: `/Users/u/.claude/plans/glowing-purring-clock.md` (phases 1–4).

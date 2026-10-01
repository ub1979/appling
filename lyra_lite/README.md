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
- **Engines plug in** through `lyra_lite/engines/base.py`. `HermesEngine` uses
  the same provider set-up as the Studio, so every linked subscription works.
- **Every turn is saved** to the project's Git with the same checkpoint the
  helpers use. Risky commands always wait in the inbox and are never
  auto-approved.

Tests:
- `scripts/run_tests.sh tests/lyra_lite` runs the real daemon, the real
  engine and a fake model server.
- `cd lyra_lite/ui && npm test` runs the UI tests.

Plan: `/Users/u/.claude/plans/glowing-purring-clock.md` (phases 1–4).

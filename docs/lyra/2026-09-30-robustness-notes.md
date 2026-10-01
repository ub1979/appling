# Robustness notes — what still lets Lyra stall or lose work

Written 2026-09-30 after a 24-hour YouTube Analytics build on this branch
(`qadir/aug28-ui-brain`, 0.19.8-a). Each item is backed by something that
actually happened; ranked by how much it would have prevented.

## Already fixed in 0.19.8-a (for reference)

Helper slots leaked on a DB error · cut-off helpers looked "done" · helpers
now auto-continue (`delegation.max_continuations`, default 2) · helper work is
auto-checkpointed · task planning is mandatory · the project map and
requirements routing read `.sdlc/progress.md` · refreshing mid-delegation no
longer opens the helper's chat · new projects go to `~/Lyra Projects`.

## Recommended next changes

### 1. Stop the coordinator from building inline (highest impact)
**What happened:** after "work on remaining things", Lyra coded in the main
chat for 1 h 41 min (02:08–03:49), used all 90 steps, then sat idle for
18 hours. No helper, no task plan, no checkpoint.
**Change:** port the *lightweight coordinator* from main (0.19.40, LYR-06):
guided project chats get the `project-guide` toolset without `terminal`, so
development can only happen through `delegate_task`. Consider also denying
`write_file`/`patch` outside `.sdlc/` and `requirements.md`.

### 2. Checkpoint at the end of every main-chat turn, not only helpers
**What happened:** the overnight turn left 14 unrecorded files; the
`subagent_stop` checkpoint never fires for the coordinator's own edits.
**Change:** fire the same `checkpoint_project` at the end of each coordinator
turn (a turn-end plugin hook, or `on_session_end` plus turn end). Cheap, and it
makes "never lose work" true for every path.

### 3. A server-side "keep going" watchdog
**What happened:** when a turn ends with work left and no helper running,
nothing restarts it. The browser's auto-continue only works while the tab is
open and connected; async-delegation completions only help once a helper is
running.
**Change:** a small scheduler (cron job or gateway timer) that, for projects
whose ledger has a `running` row, no active delegation, and a last reply that
is not a question or approval checkpoint, submits one continuation turn — with
a daily cap and a "stop" switch in the Studio.

### 4. A safe way for supervisors to send a message
**What happened:** I could not drive Lyra overnight. `prompt.submit` over
`/api/ws` rebinds the session's output to the caller, and when that socket
closes the session is reaped 20 s later (`HERMES_TUI_WS_ORPHAN_REAP_GRACE_S`).
Only `session.steer` is safe, and it only works mid-turn.
**Change:** add `session.enqueue` (queue a prompt as the next turn without
touching the transport), or let `prompt.submit` take `rebind_transport: false`.
Items 3 and 4 together make unattended builds possible.

### 5. Old chats keep old rules
**What happened:** the YouTube chat kept the app-it text from its start, so
tonight's rule changes (task planning, returning-to-project) did not apply
until the user pasted "reload your rules".
**Change:** store the app-it version on the session; when it changes, show a
Studio notice "Project rules were updated — apply now?" that sends the
reload on the user's next turn (cache-aware, like `/skills install --now`).

### 6. Warn loudly when the chat cannot be saved
**What happened:** `state.db` was corrupt from 22:07 to 00:37; every message
failed to save with only a log warning, so ~2.5 h of conversation vanished and
Lyra later forgot the approved requirements.
**Change:** after N consecutive `Session DB append_message failed`, show a red
banner ("This conversation is not being saved") and pause new delegations.
Also schedule a daily `state.db` backup (it has been corrupted twice: Sep 8
and Sep 29).

### 7. One SQLite across all Lyra copies
This checkout's `.venv` (uv CPython 3.12.9) links SQLite 3.47.1, which has the
WAL-reset corruption bug; the main checkout's managed runtime has 3.53.1 and
switches the DB back to WAL. Rebuild this `.venv` on a Python with SQLite
≥ 3.51.3 (Homebrew `python@3.13` has 3.53.4, or update `uv`), or never run the
two copies at once.

### 8. Tell the owner about owner-only setup, step by step
**What happened:** "Once you authorize your channel" hid a real job (create a
Google Desktop OAuth client ID, set `YOUTUBE_CLIENT_ID`). Add an app-it rule:
anything only the owner can do is presented as numbered steps with where to
click, never a one-line "once you …".

### 9. Smaller things
- `stop.sh` finds Lyra by its listening port, so a dashboard paused with
  Ctrl+Z (no listener, still holding `state.db`) is invisible; find it by
  process and cwd instead, and have `start.sh` warn about a stopped instance.
- Self-review turns used ~11 % of model calls (79 of ~690); raise
  `skills.creation_nudge_interval` for guided project chats.
- Each helper spends ~5 steps re-reading notes; pass a short handoff (ledger
  row + brain excerpt + file list) in the delegation context.
- The keep-alive PTY key includes `resume`; any resume rewrite spawns a second
  TUI on the same conversation. Keying on token + workspace would be sturdier.
- Fix the 18 long-standing failures in `tests/hermes_cli/test_web_server.py`
  so new regressions stand out.
- The YouTube OAuth exchange sends no client secret; Google Desktop clients
  usually require one. Verify against real Google before calling it done.

## Agreed direction (2026-10-01): files-first rebuild, after the YouTube app

Most failures came from the plumbing, not the skills: the Studio drives a
hidden TUI through a PTY, decides readiness by scanning the terminal for `❯`,
receives events over a separately named side channel, and spreads state over
browser storage, the PTY registry, in-memory gateway sessions, `state.db`, the
ledger and Git. When they disagree the user sees a bug.

Plan (owner decision: build after the YouTube app is finished):
1. Per-project `.lyra/` as the single source of truth: append-only
   `events.jsonl`, `inbox/` (approvals, questions, owner actions — one file
   each, answered by a file), `tasks/` (one file per task), plus
   `.sdlc/progress.md` and Git.
2. Studio sends messages through a small direct API and renders by tailing the
   files — no PTY, no screen scraping; refresh/sleep/restart lose nothing.
3. Engines (Hermes, Claude Agent SDK) write the same files (fits
   `qadir/claude-engine`).
4. Light UI: chat, activity, project map, owner inbox. Skills unchanged.
Trade-off: diverges from upstream Hermes' "embed the TUI" guidance.

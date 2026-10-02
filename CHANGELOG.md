# Changelog

What changed in each release of Lyra, newest first. The top entry's version must
match `LYRA_VERSION` in `lyra_version.py` — a test enforces it, so bumping one
without the other fails the build rather than shipping a lie.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are `MAJOR.MINOR.PATCH` with an optional pre-release suffix (`-a`); the channel records the release's maturity.

## [Unreleased]

### APP IT (next) — live preview, pick to change, phone apps

- **Live preview beside the chat**: ▶ opens your app in a panel next to the
  conversation, at computer or phone size, with reload, open-in-tab and the
  app's own error messages.
- **🎯 Pick**: point at any part of the app in the preview; it joins your
  message ("make this bigger") with what APP IT needs to find it in the code.
- **Where will people use it?** New apps choose Web, Phone and/or Computer.
- **Phone apps with Expo Go**: phone apps are built with Expo; the preview
  panel shows a QR code — scan it with Expo Go and the app runs on your phone,
  updating live as APP IT works. New `mobile-expo` playbook for the agents.

### APP IT v0.03 beta — 2026-10-02

Lyra Lite is now **APP IT**: a new name on every screen and in the assistant's
own words (internal folder and code names stay `lyra` so existing projects
keep working).

Websites, templates and real checks:

- **What are you making?** New projects choose App, Website, Slides or Video.
  Websites skip the build-size question.
- **Twelve website templates, each with a live demo** (Cinematic Parallax,
  3D Product Launch, Editorial Scroll Story, Creative Portfolio, SaaS Launch,
  Kinetic Type, Stacked Cards, AI / Tech Company, Restaurant & Food,
  Architecture & Property, Charity & Impact, Beauty & Wellness Shop), plus
  your own private templates. Requirements starts from the chosen design and
  asks only what to change.
- **Websites are checked like a visitor sees them.** A site check opens the
  build in Chrome on a computer and a phone, scrolls it, flags errors,
  sideways overflow and text that never appears, and puts it side by side with
  the template's demo. QA can no longer approve a page it never opened.
- **Open app actually opens the app.** Lyra builds the site when needed and
  serves it at its own address, so built sites load their styles and scripts.
- Chat jumps to your message when you send; "↓ Latest" when reading above.
- New skills: web-cinematic (premium scroll sites) and business-motion-film
  (from motion-video-kit, MIT).
- **Photo-real website templates** (Grand Reveal, Lunar Parallax): your
  video played frame by frame as you scroll, or six layers of photos. Lyra
  asks for your video, frames or photos, or makes AI pictures on your
  ChatGPT plan (`.lyra/kit/imagine`, `cutout`, `frames`).
- **📎 Attach files in chat** (button, drag and drop, paste) — saved in the
  project's `assets/uploads/`.
- **Presentation templates** (Investor Pitch, Keynote Story, Data Report,
  Workshop): HTML decks on reveal.js with live demos and PDF export.
- **Video templates** (8 film styles) built from the HyperFrames registry
  (Apache-2.0) with preview videos; rendered locally with telemetry off.
- **Colour & UX skill** with a palette checker (contrast, colour-blind
  clashes, shade ramps). Claude Code now also gets the shared design skills;
  Hermes now gets the UI designer, UX writer and accessibility playbooks.

### Lyra Lite v0.02 beta — 2026-10-01

Memory that keeps each project focused — and stays inside that project.

- **No more memory leaking between projects.** Lyra Lite no longer uses
  Hermes' shared memory notes or searches other chats; details from one
  project can't drift into another.
- **Project focus note.** Every message Lyra gets carries a short "where we
  are" from the project's own files (current step, what's left, next
  actions, open questions) — re-sent only when it changes. Long chats can be
  summarised without Lyra losing track.
- **Project recall.** A searchable memory per project (`.lyra/memory.db`):
  the whole chat with the owner, requirements, plans, progress, agent reports
  and Git history. Lyra and her agents look things up with `project_recall`
  instead of guessing or asking again. Works on Hermes and Claude Code.
- **About me** (AI settings): the one thing Lyra carries between projects,
  written only by the owner.
- **Claude Code engine** loads Lyra's playbooks as native skills (one
  question at a time in requirements; never re-asks the build size), and
  can run on the owner's Claude plan, Ollama or an API key.
- Settings page with engine/model choice; round icon buttons; `./start.sh`
  and `./stop.sh` run Lyra Lite.

### Lyra Lite v0.01 beta — 2026-10-01

A new, lighter Lyra (`./lyra.sh`, <http://127.0.0.1:9200/>) beside the Studio.
Same projects, linked models and builder playbooks; new plumbing.

- **Files are the truth.** Each project keeps `.lyra/` (activity log,
  conversation, append-only transcript, inbox, state). Refresh, sleep or a
  restart lose nothing; long chats are never cut by summarising.
- **No hidden terminal.** The engine runs directly; the screen follows a live
  feed. Studio look: start page, project set-up with your own team and a
  build size (Personal / Reusable / Production), project studio with team,
  map, token use and activity, round icon buttons.
- **Engines:** Hermes (any linked subscription — Codex, Claude Code CLI,
  Ollama, Copilot …) or Claude Code (Anthropic API key or Ollama), chosen in
  the AI settings, per project if wanted.
- **Lighter Lyra:** she coordinates without a shell; agents build, test and
  commit; parallel tasks; short handoffs and a Project Brain; plans and QA
  sized to the project.
- **Never stuck or silent:** keep-going watchdog, Stop that really stops,
  approvals for agents' risky commands, ready banner, Open app, notifications.
- **Fixed in Hermes:** a helper's flagged command no longer gets parked
  unseen — the approval now reaches the owner (single and parallel helpers).

## [0.19.8-a] - 2026-09-30 — Background helper reliability

### Fixed

- **A damaged session database no longer forces every helper to block the
  chat.** When saving a background helper's record failed, its slot was never
  released; after three failures every later helper ran in the foreground for
  the rest of the session. The slot is now freed and the helper runs in the
  foreground only that once. A failed save when a helper finishes no longer
  loses its result.
- **A helper that runs out of steps now says so.** Its result keeps its
  summary but carries a plain note that it was cut off, so the project chat
  reports unfinished work instead of treating it as done.
- **The Agent activity panel no longer cuts off on the right.** Long titles
  end in "…" and the "Stop tool & retry" button wraps inside the panel.
- **Recent project cards display properly again.** The letter badge was
  squeezed into a tall pill and long names and folder paths were cut off on
  the left; the card now shows a full-width banner and left-aligned text.
- **Reopening a project picks up where it really left off.** Lyra now treats
  the project's own files (progress ledger, approved requirements, Git state)
  as the record instead of chat history, never re-asks questions from a
  finished phase, and tells you about unfinished or unsaved work and asks
  whether to finish it before starting something new.
- **The activity panel names the right agent.** Development tasks that
  mention testing were shown as "Quality assurance agent is working"; an
  agent is now named once from its task, not re-guessed from each step.
- **The Project map shows real progress after a lost chat.** It showed 0/6
  for a project with three verified phases, because it only remembered what
  this browser saw. It now also reads the project's own progress file when a
  project opens and after each reply.
- **Refreshing during background work no longer opens the wrong chat.** A
  refresh while a helper was running switched the page to the helper's own
  conversation and started a second copy of Lyra on it, leaving Send stuck
  behind "Lyra is still starting" and hiding the helper. Helper conversations
  are no longer treated as a continuation of the main chat, and a reconnected
  chat now redraws its screen so Send unlocks when Lyra is idle.
- **An old tab that points at a helper's conversation reopens the main chat.**
- **The Studio no longer goes deaf after a dropped connection.** When the
  page's live-update connection dropped (sleep, network blip) and reconnected,
  it stopped receiving Lyra's updates — including approval requests, so Lyra
  silently waited for an answer nobody could see. The link is now kept.
- **The Project map reads free-form progress notes.** Phases written as
  "verified document", "Remaining development | running" or
  "security / QA | partial" showed as Next; the map now recognises the phase
  words in a row and verified/partial/pending wording.
- **Lyra fixes problems it is allowed to fix instead of reporting them.** A
  new rule: when a fix stays within the approved requirements, is reversible
  and needs nothing only the owner has, Lyra makes it and says so in one line.
- **When Lyra needs you to do something, it gives numbered steps.** Where to
  go, what to click, and what to send back — instead of a one-line status such
  as "pending your signed-in Update analysis run".
- **The agent panel shows when Lyra works without helpers.** Instead of "No
  workers" while Lyra was busy, it says "Lyra working directly" and what it is
  doing.
- **A brief AI outage no longer stalls harmless commands.** If the automatic
  safety check for a flagged command fails on a connection drop or timeout,
  it tries once more after a short pause before asking you.

### Changed

- **A helper that runs out of steps now keeps going.** Instead of stopping
  half-way, it gets up to two more full rounds on the same task
  (`delegation.max_continuations`, default 2). Only a task that still cannot
  finish is reported as cut off, with a note to split it.
- **Helpers' work is saved automatically.** When any helper stops, whatever it
  changed in a builder project is recorded in that project's own Git history
  as a clearly labelled checkpoint. Password and key files are never included,
  and Lyra's own code is never touched.
- **New projects are created outside Lyra's folder.** The New project screen
  now starts in `~/Lyra Projects` (created automatically), refuses to create a
  new project inside Lyra's own folder, and the folder picker has a
  "New folder" button. Existing projects there still open normally.
- **Task planning is always part of the team.** Every project gets a task plan
  before development, with tasks sized to finish within one helper and
  labelled with the files they own, so independent tasks can run in parallel.

## [0.19.7-a] - 2026-09-23 — Model switching and send fixes

### Fixed

- **Changing the AI model mid-project now reaches the open project chat.** A
  resumed chat no longer treats its old model as a locked choice: the next
  message runs on the model chosen in AI model settings. A model you pick
  with `/model` is still respected, and desktop chats keep their own models.
- **An old model is never sent to a different provider.** A resumed session
  whose provider was lost used to pair its old model with the newly selected
  provider (e.g. `glm-5.2:cloud` sent to Codex, failing with HTTP 400). Such a
  model is now dropped and the configured provider and model are used together.
- **The Send button no longer stays disabled after a slow start.** The chat
  keeps checking until Lyra is ready instead of giving up after 15 seconds,
  and says so if startup is slow.

### Changed

- Versions may carry a pre-release suffix (`0.19.7-a`).

## [0.19.6] - 2026-09-21 — Aug 28 UI and Brain comparison

### Added

- **Comparison build with modern Studio UI and bounded Project Brain.** This
  branch keeps the 28 August direct specialist workflow while adding the newer
  visual shell and compact, evidence-linked project memory. Later mandatory
  Kanban project runs are intentionally absent so end-to-end build behaviour
  can be compared directly.

## [0.19.5] - 2026-08-28 — reliable long model waits

### Fixed

- **Long model turns no longer get falsely stopped after two minutes.** Guided
  chat now treats the backend's 30-second waiting heartbeat and streamed model
  reasoning as genuine activity. The live card explains that the provider is
  still working, and the silence watchdog remains available for requests that
  actually stop reporting.

## [0.19.4] - 2026-08-28 — visual researcher agent

### Added

- **Researcher is now a full visual App Builder agent.** It appears in both
  agent-selection screens with selected and unselected raccoon portraits, has
  its own project phase and `research-report.md` handoff, and can be recommended
  for markets, competitors, standards, unfamiliar domains, and technical
  choices that need verified external evidence. Its project playbook reuses the
  canonical Researcher skill so the research method has one source of truth.

## [0.19.3] - 2026-08-28 — researcher

### Added

- **Researcher — dependable internet research as one built-in skill.** It
  plans searches from several angles, reads the underlying pages instead of
  trusting snippets, prefers primary sources, verifies important claims,
  reconciles contradictory evidence, checks freshness, and returns direct
  citations with uncertainty made explicit. Native web tools are the default;
  DuckDuckGo, SearXNG, arXiv, and Parallel remain focused supporting options.

## [0.19.2] - 2026-08-27 — safer remote projects

### Fixed

- **"Operation interrupted: waiting for model response" is no longer shown as
  Lyra's reply.** That sentence is internal bookkeeping the conversation loop
  writes whenever a turn is cancelled mid-request — which happens every time a
  message arrives while the previous turn is still running, including the
  dashboard's own automatic continuation turns. ACP and the gateway chat
  surfaces already dropped it; guided chat rendered it, so people read it as
  "Lyra stopped", sent another message, cancelled the next turn, and saw it
  again. It is now stripped at both the terminal-scrape and the response-text
  stage.

- **Startup no longer nags about an unhealthy venv it never checked.** Lyra
  looked for its virtual environment at `venv/`, but `start.sh` creates `.venv`
  (uv's default) — so on every install the health probe found no interpreter,
  reported "cannot tell" instead of an answer, and left the
  `.lazy-refresh-incomplete` marker on disk. Result: the warning
  "a previous lazy-backend refresh may have left the venv unhealthy" reprinted
  on every single launch, forever, while nothing was ever actually verified.
  The venv is now located rather than assumed (`hermes_cli/venv_paths.py`), and
  the same fix un-blinds the SQLite runtime repair and the service PATH, which
  were silently opting out on `.venv` installs for the same reason.
- **A cold start no longer looks like a hang.** `start.sh` discarded the output
  of the plugin-enable step, so the slowest part of a first run printed one line
  and then went silent for minutes. It now shows its work, and says up front
  that a first run compiles dependencies and can take a while.
- **Telegram setup is private and easier to understand.** Remote setup now
  explains who can use the linked bot, guides the owner through the required
  steps, prevents accidental public access, and correctly handles Telegram's
  disabled group policy instead of treating `FALSE` as an allow-list entry.

### Added

- **Remote — a settings page that puts Lyra on your phone.** Telegram used to
  mean editing `.env` by hand and running `hermes gateway install` in a
  terminal, which is where most people stopped. Now: paste the one thing
  Telegram will only give a human (the token from @BotFather) and Lyra does
  the rest — saves it, switches the channel on, installs the background
  service, starts it, and watches until your phone actually answers. The
  service survives closing the window and a reboot. Steps appear one at a
  time, with the full guide behind "Show me everything". The Channels page is
  unchanged for anyone who wants the per-variable controls.
- **Copy button on every chat message.** Each bubble carries a small copy icon —
  hover to reveal on desktop, always visible on touch. Lyra's replies copy as
  their original markdown, so code blocks, lists and formatting survive being
  pasted somewhere else; internal phase markers never do.
- **Project changes are committed locally by default.** Lyra's project-building
  guidance now requires a local Git commit after each completed change set,
  while remote pushes remain explicit user actions.
- **One product version everywhere.** The dashboard, desktop package, App
  Builder source, built bundle, release API, and tests now agree on Lyra's
  version, without changing the separate upstream Hermes CLI version.

## [0.17.0] - 2026-08-21 — base code

- Base code. This is the baseline every later release is measured against:
  guided chat, the agent roster and its playbooks, the skills library, and the
  dashboard as they stand today.
- Versioning starts here — from now on every release records what changed and
  why, and the running version is visible in the app.

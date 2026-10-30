# Changelog

What changed in each release of Appling and its compatibility runtime, newest
first. The top entry's version must match `LYRA_VERSION` in `lyra_version.py` —
a test enforces it, so bumping one without the other fails the build.

Format: [Keep a Changelog](https://keepachangelog.com/en/1.1.0/).
Versions are `MAJOR.MINOR.PATCH` with an optional pre-release suffix (`-a`); the channel records the release's maturity.

## [Unreleased]

### Appling v0.15 beta — 2026-10-30

- Replaced the mixed Appling/Lyra onboarding with current install, model setup,
  project creation, privacy, and cost guidance.
- Updated Appling's technical, testing, and contribution guides and GitHub
  forms. Public issue reports no longer require diagnostic uploads.
- Preserved historical internal paths needed by existing projects.
- Added a dedicated Appling desktop launcher and native installer builds for
  macOS, Windows, and Linux. First launch prepares Python, Node.js, and npm;
  updates keep project folders separate from the application.

### Appling v0.14 beta — 2026-10-28

- **Hermes runs every project.** Removed the Claude Code engine, its SDK dependency,
  installation steps and engine settings. Hermes model providers remain available.
- **Safe upgrades from older installations.** Retired Claude settings are backed up;
  existing Claude project state moves to Hermes with history intact and continuation
  paused until the next owner message. Old approvals expire during restart recovery.
  Updating does not delete projects.
- **Existing fixes retained.** Progress-status parsing, owner approval handling,
  retry continuity and completed-work QA protections remain in place. Skills,
  helper budgets and Security/Code Review/QA gates are unchanged.
- Verified with 220 Appling backend tests, 10 UI tests and a production UI build.

### Appling v0.13 beta — 2026-10-28

- **Negated completion stays unfinished.** Statuses such as `not fully fixed`
  and `not completely confirmed` cannot mark a phase done. Work awaiting owner
  acceptance or approval stays in the owner state without an automatic nudge.
- **Historical failures require evidence of resolution.** `Previously failing`
  or `previously open` alone no longer clears a problem. Explicit fixes or
  resolutions in the same clause retain their completed status; remaining
  problems stay visible in the map, coordinator focus and continuation checks.
- Skills, helper budgets, review gates and the existing handling of partially
  complete work remain unchanged.

### Appling v0.12 beta — 2026-10-27

- **More QA wordings read correctly.** `fixed, no longer failing`,
  `PASS (previously failing test fixed)`, `PASS — 0/5 failing` and
  `CONFIRMED at <commit>` count as finished; `PASS — Safari test fails`,
  `not confirmed` and `not yet fixed` stay unfinished, and "partially fixed"
  or "partially complete" is no longer counted as done.
- Checked against every progress ledger on the build Mac: only the intended
  `CONFIRMED` rows change, and no project's keep-going decision changes.
- Skills, helper budgets and Security/Code Review/QA gates remain unchanged.

### Appling v0.11 beta — 2026-10-27

- **Passed QA stays finished.** Statuses such as `PASS — 0 open HIGH/CRITICAL`,
  `APPROVED, no open defects` and `verified, nothing pending` no longer reopen
  work in the project map, coordinator focus or idle keep-going checks.
- **Failures remain unfinished.** Explicit FAIL/failed/failing results override
  completion words such as done or completed. Real remaining work and pending
  owner approvals retain their existing handling.
- **Checker regression test waits for setup.** The test now completes the
  project's setup turn before customizing its checkers and counting the two
  status turns, removing the timing race on both engines.
- Skills, helper budgets and Security/Code Review/QA gates remain unchanged.

### Appling v0.10 beta — 2026-10-27

- **Project QA checkers keep their customizations.** Status requests and helper
  reports no longer overwrite project-specific site/deck checks. Untouched
  managed copies still receive bundled updates; unknown legacy copies are
  preserved and missing checkers are installed.
- **Coordinator compression keeps the right amount of history.** Applying the
  coordinator's token cap now resizes the retained tail using the compressor's
  configured ratio, while preserving lower caps and model-switch behavior.
- **Approval prompts follow their own requests.** Background approvals survive
  unrelated chat turns, expire on timeout or Stop, and resolve the selected
  request even when several helpers ask in a different order.
- **Progress follows the ledger's actual columns and current records.** Later
  phase results supersede older rows. Explicit delivery closes earlier stale
  rows only in the same table and revision; new, reopened and unrelated work
  still continues. Old current/next notes cannot restart delivered work.
- Skills, engine selection, Security/Code Review/QA gates and helper budgets
  remain unchanged.

### Appling v0.09 beta — 2026-10-23

- **Ollama appears on fresh installations.** Appling Settings discovers models
  from Ollama running on this computer on first load and Refresh, even before
  the provider has been configured. Selecting a model uses the existing
  keyless local connection; other pickers and the build/QA workflow keep
  their existing behavior.

### Appling v0.08 beta — 2026-10-23

- **Each project keeps its engine.** The engine is locked when the project is
  created or first opened after this update. Global engine changes apply only
  to new projects; existing conversations and helpers stay with their engine.
- **Hermes retries remember running helpers.** A coordinator error preserves
  its working conversation and dispatch details. The next turn receives the
  current running-job list; repeating an identical running task returns its
  existing job instead of starting another worker. Unrelated work and later
  retests after completion continue normally.
- **Closed work stays closed in the project map.** Resolved, superseded and
  descoped rows are no longer shown as unfinished unless they explicitly
  remain incomplete or blocked. QA stages and approval rules are unchanged.

### Appling v0.07 beta — 2026-10-21

Browse opens your computer's own folder dialog, Appling runs on Windows with
`start.bat`, and new projects go to `~/Appling Projects`.

- **Browse uses your computer's folder dialog**: choosing where a project
  lives, or which folder to open, now shows Finder on a Mac, Explorer on
  Windows and the GTK/KDE dialog on Linux (needs `zenity` or `kdialog`).
  Where there is no dialog — or Appling is open on another device, such as a
  phone — Appling's own folder list appears as before.
- **New projects go to `~/Appling Projects`** (was `~/Lyra Projects`).
  Projects already in the old folder keep working where they are.
- **Windows**: `start.bat` prepares and starts Appling in the background and
  `stop.bat` stops it (log in `%LOCALAPPDATA%\hermes\logs\appling.log`).
  Stopping a phone preview no longer fails on Windows.
- **Other websites can no longer reach Appling**: a page that re-points its
  own domain at Appling's port could read Appling's private key and send it
  messages. Appling now answers only when opened by IP address or
  `localhost` (`http://<name>.local:9200` is refused — use the IP).
- **The red problem bar no longer outlives a restart**: a problem from before
  Appling restarted is not shown again, and the bar has a × to hide it.
- **Your own templates show their thumbnail**: a private template with
  `demo/thumb.jpg` now shows it in the library, like the built-in ones.
- **The Claude Code engine is split into small modules** (model routes,
  turn handling, helpers, permissions, playbooks) with no change in how it
  works. A reply now still ends if saving it fails, or if the Claude program
  stops while Appling is closing a helper report, instead of staying "busy".

### Appling v0.06 beta — 2026-10-13

You can always talk to Appling while its helpers work, it no longer gets
stuck, and it always offers the newest Claude models.

- **Always the newest Claude models**: the model lists for "Your Claude
  plan" and "Anthropic API key" now ask Anthropic which models your account
  can use, newest first (Opus 5.5, Sonnet 5.5, Haiku 5.5, Fable 5.1 today),
  so new releases appear without an Appling update. A new Appling version no
  longer shows an hour-old saved list.
- **`./start.sh` gives the Terminal back**: Appling runs in the background
  (log in `~/.hermes/logs/appling.log`) and keeps running if the Terminal
  closes; stop it with `./stop.sh`. It also installs the Claude Code engine
  if it is missing, instead of failing on the first Claude reply with
  "No module named 'claude_agent_sdk'".
- **Choose how hard the model thinks**: Settings has an Effort choice next to
  the model, on both engines — low, medium, high, extra high or max (Hermes
  can also turn thinking off). Nothing chosen means **high**, never more:
  without it, Opus 5.5 ran at medium and Hermes on older Claude models didn't
  think at all. Applies from the next message.
- **You can always talk to Appling on Claude Code**: helper agents now run in
  the background, as on Hermes. Appling's reply ends as soon as it has
  started them, so your next message is answered straight away instead of
  waiting hours for a whole wave; each helper's report arrives as its own
  short message. Stop also stops background helpers. When a reply fails,
  Appling shows Claude's own words (for example "You've hit your session
  limit · resets 12:20am") instead of "Claude engine: success".
- **Appling no longer gets stuck "working" after a helper report**: a
  usage notice from Claude Code between replies used to open a reply nothing
  would ever finish, so new messages waited in the queue for hours. Notices
  no longer start a reply, a reply left open is closed when the next one
  begins, and Stop always ends the reply within 15 seconds.
- **Five new website templates**, each with a live demo: **AI Product**
  (an assistant answering live with sources), **Software Product** (bento
  grid, light/dark switch), **Landing Page** (one offer, one button),
  **New Company** (a calm, credible first site) and **Developer Tool**
  (install command, live terminal, code tabs). Templates are folders in
  `lyra_lite/templates/` — adding or removing one needs no code change.
- **Two new slide templates**: **Sales Demo** (the customer's outcome,
  before/after, three capabilities with product screens, a pilot and one
  next step) and **Company Intro** (who we are, how we work, results, a
  growing timeline, team and studios).
- **Two new video templates**: **Social Captions Reel** (vertical, bold
  word-by-word captions that work muted) and **Announcement** (6–15 s: a
  split-flap reveal, a headline that lands, one detail, your logo).

### Appling v0.05 beta — 2026-10-11

Three new studio agents for the things Appling makes besides apps. Each
appears in the team picker and is the default builder for its project kind.

- **Website studio** (`website-builder`): professional product and company
  sites — blueprints for AI products, software/SaaS, one-offer landing
  pages, new companies and developer sites; headline, proof and call-to-action
  rules that never invent customers or numbers; real screens first, AI
  pictures (on your ChatGPT plan) only with your yes; a quality checklist for
  speed, light/dark contrast, phones, accessibility and sharing. Parallax and
  scroll films still use the cinematic playbook.
- **Presentation studio** (`deck-builder`): story structures (pitch, sales
  demo, company intro, report, keynote, lesson, proposal), slide design and
  chart rules. A new **deck check** opens the deck in Chrome, shows every
  slide with all its build-ups, flags text that runs off a slide, tiny text
  and crowded slides, and exports a one-page-per-slide PDF. Decks without a
  template are still PowerPoint by default.
- **Video studio** (`video-builder`): launch clips, app promos, social
  reels, explainers, announcements and data stories with HyperFrames;
  timing in frames, reading holds, three stills approved before animating,
  fixes written against exact frames, and export checks (size, frame rate,
  loudness). Premium 3D commercials still use the business film playbook.
- The Data Report deck template's source lines are 16 px, so the template
  passes its own deck check.

### Appling v0.04 beta — 2026-10-02

APP IT is now **Appling** — a little app that grows. New name on every screen
and in the assistant's own words; the app's folder is now `my_lyra/appling`.

Live preview, pick to change, phone apps:

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

## [0.19.17-a] - 2026-10-30 — Appling desktop installers

Appling v0.15 beta; the Studio compatibility version advances to 0.19.17-a.

- Added a dedicated Appling launcher, first-run dependency setup, native
  packaging workflow, and packaged-runtime smoke checks.
- The separate Hermes desktop client retains its own interface.

## [0.19.16-a] - 2026-10-30 — Appling documentation and onboarding

Appling v0.15 beta; the Studio compatibility version advances to 0.19.16-a.

- The README, contributor guide, technical walkthrough, and GitHub issue forms
  now match the current Appling workflow and repository.
- Internal project paths remain compatible.

## [0.19.15-a] - 2026-10-28 — Hermes-only Appling

Appling v0.14 beta; the Lyra/Studio compatibility version advances to 0.19.15-a.

- **Hermes runs every project.** Removed the Claude Code engine, its SDK dependency,
  installation steps and engine settings. Hermes model providers remain available.
- **Safe upgrades from older installations.** Retired Claude settings are backed up;
  existing Claude project state moves to Hermes with history intact and continuation
  paused until the next owner message. Old approvals expire during restart recovery.
  Updating does not delete projects.
- **Existing fixes retained.** Progress-status parsing, owner approval handling,
  retry continuity and completed-work QA protections remain in place. Skills,
  helper budgets and Security/Code Review/QA gates are unchanged.
- Verified with 220 Appling backend tests, 10 UI tests and a production UI build.

## [0.19.14-a] - 2026-10-28 — Keep unfinished QA and owner acceptance visible

Appling v0.13 beta; the Lyra/Studio compatibility version advances to 0.19.14-a.

- **Negated completion stays unfinished.** Statuses such as `not fully fixed`
  and `not completely confirmed` cannot mark a phase done. Work awaiting owner
  acceptance or approval stays in the owner state without an automatic nudge.
- **Historical failures require evidence of resolution.** `Previously failing`
  or `previously open` alone no longer clears a problem. Explicit fixes or
  resolutions in the same clause retain their completed status; remaining
  problems stay visible in the map, coordinator focus and continuation checks.
- Skills, helper budgets, review gates and the existing handling of partially
  complete work remain unchanged.

## [0.19.13-a] - 2026-10-27 — Fewer misread QA statuses

Appling v0.12 beta; the Lyra/Studio compatibility version advances to 0.19.13-a.

- **More QA wordings read correctly.** `fixed, no longer failing`,
  `PASS (previously failing test fixed)`, `PASS — 0/5 failing` and
  `CONFIRMED at <commit>` count as finished; `PASS — Safari test fails`,
  `not confirmed` and `not yet fixed` stay unfinished, and "partially fixed"
  or "partially complete" is no longer counted as done.
- Checked against every progress ledger on the build Mac: only the intended
  `CONFIRMED` rows change, and no project's keep-going decision changes.
- Skills, helper budgets and Security/Code Review/QA gates remain unchanged.

## [0.19.12-a] - 2026-10-27 — Accurate QA completion status

Appling v0.11 beta; the Lyra/Studio compatibility version advances to 0.19.12-a.

- **Passed QA stays finished.** Statuses such as `PASS — 0 open HIGH/CRITICAL`,
  `APPROVED, no open defects` and `verified, nothing pending` no longer reopen
  work in the project map, coordinator focus or idle keep-going checks.
- **Failures remain unfinished.** Explicit FAIL/failed/failing results override
  completion words such as done or completed. Real remaining work and pending
  owner approvals retain their existing handling.
- **Checker regression test waits for setup.** The test now completes the
  project's setup turn before customizing its checkers and counting the two
  status turns, removing the timing race on both engines.
- Skills, helper budgets and Security/Code Review/QA gates remain unchanged.

## [0.19.11-a] - 2026-10-27 — Reliable approvals, progress and QA checkers

Appling v0.10 beta; the Lyra/Studio compatibility version advances to 0.19.11-a.

- **Project QA checkers keep their customizations.** Status requests and helper
  reports no longer overwrite project-specific site/deck checks. Untouched
  managed copies still receive bundled updates; unknown legacy copies are
  preserved and missing checkers are installed.
- **Coordinator compression keeps the right amount of history.** Applying the
  coordinator's token cap now resizes the retained tail using the compressor's
  configured ratio, while preserving lower caps and model-switch behavior.
- **Approval prompts follow their own requests.** Background approvals survive
  unrelated chat turns, expire on timeout or Stop, and resolve the selected
  request even when several helpers ask in a different order.
- **Progress follows the ledger's actual columns and current records.** Later
  phase results supersede older rows. Explicit delivery closes earlier stale
  rows only in the same table and revision; new, reopened and unrelated work
  still continues. Old current/next notes cannot restart delivered work.
- Skills, engine selection, Security/Code Review/QA gates and helper budgets
  remain unchanged.

## [0.19.10-a] - 2026-10-23 — Fresh-install Ollama discovery

Appling v0.09 beta; the Lyra/Studio compatibility version advances to 0.19.10-a.

- **Ollama appears on fresh installations.** Appling Settings discovers models
  from Ollama running on this computer on first load and Refresh, even before
  the provider has been configured. Selecting a model uses the existing
  keyless local connection; other pickers and the build/QA workflow keep
  their existing behavior.

## [0.19.9-a] - 2026-10-23 — Project engine locks and safe retries

Appling v0.08 beta; the Lyra/Studio compatibility version advances to 0.19.9-a.

- **Each project keeps its engine.** The engine is locked when the project is
  created or first opened after this update. Global engine changes apply only
  to new projects; existing conversations and helpers stay with their engine.
- **Hermes retries remember running helpers.** A coordinator error preserves
  its working conversation and dispatch details. The next turn receives the
  current running-job list; repeating an identical running task returns its
  existing job instead of starting another worker. Unrelated work and later
  retests after completion continue normally.
- **Closed work stays closed in the project map.** Resolved, superseded and
  descoped rows are no longer shown as unfinished unless they explicitly
  remain incomplete or blocked. QA stages and approval rules are unchanged.

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

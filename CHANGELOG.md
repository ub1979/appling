# Changelog

Appling C is an independent rewrite of Appling. Its history is separate from
the original Appling `main` branch.

## Branches

| Branch | What it is |
|---|---|
| `main` (pushed as `appling_c`) | Current Appling C. New projects build in **direct mode**. Blocks mode is still available on request. |
| `block_branch` | New projects default to **blocks mode**, with interfaces agreed first and a serial fallback. Direct mode can be chosen at setup. |

## 2026-11-25: reliability fixes and a build-mode choice

**Fixes (both branches):**
- A builder that edits approved files (requirements, checks, prototype, block
  plan) no longer leaves the project stuck. Appling puts the approved version
  back and tells the owner.
- Claude and Copilot tasks end after 30 minutes of silence, not 30 minutes in
  total.
- A missing or signed-out Codex, Claude or Copilot is reported in plain words
  before any work starts.
- Planned-mode repair tasks no longer fail with "Task ownership is missing".
- A project whose folder is gone can be deleted. The delete message names the
  real Archive folder.
- Work copies of finished reviews and integrated workers are removed.
- Progress updates count steps from engines other than Codex.
- Apps may not point into Appling's own folder. Files that do are sent back
  to the builder.
- `/change` and `/replan` explain themselves on a direct project.
- Programs left running by a force-quit or crashed Appling (AI programs, test
  commands, phone previews) are stopped at the next start. Appling records
  each program it starts and signals one only when its process id and start
  time both match the record. Anything it cannot prove is its own is left
  running and named in the server log.

**New:** the setup form asks how to build the app: one builder step by step,
or blocks built in parallel. Settings lists blocks mode too.

**Not done:** leftovers from a crash that happened before this fix are not
cleaned, because nothing recorded them. The WhatsApp bridge and helper
processes that share Appling's own process group are not recorded either.

**Validation:** backend and interface test suites pass. The setup form and
Settings changes were type-checked and built but not checked in a browser.

## 0.2.0 beta, 2026-11-21: direct mode is the default again

**What changed:** new projects follow requirements → clickable design → one
builder → independent QA. The builder runs on Codex with its native helpers
turned on, so Codex can start parallel subagents when that helps. Existing
projects keep the mode they were created with.

**Why:** blocks mode worked end to end on two real projects, but nearly every
real run uncovered a new problem in the extra stages: the block plan, the
merge step and library reuse. Small apps don't need those stages, and fewer
moving parts means fewer places to fail. Blocks mode stays in the code, and
`block_branch` keeps it as the default.

## 0.2.0 beta, 2026-11-19 to 2026-11-20: blocks mode

This build mode splits an app into reusable blocks.

**How it works:**
- A planner splits the approved requirements into independent blocks plus a
  project-specific body.
- Blocks are built in parallel. Appling runs each block's own tests itself.
- Blocks that pass are saved to a shared library at `~/.appling/blocks/`. A
  saved block is marked verified once it passes unchanged in a second project.

**Owner controls:**
- A stuck block can be left for later without stopping the rest.
- The owner can type instructions for a stuck block.
- `/change` updates the requirements after a build and rebuilds only the
  parts that changed.

**Fixes from the real runs:**
- Library blocks are installed before they are tested.
- Blocks with hidden imports are not saved to the library.
- A reused block must bring the blocks it depends on.
- The project lockfile is refreshed for workspaces.

**Other changes:**
- Small apps get small plans.
- The requirements writer adds only the checks the owner needs.
- A "decide small questions for me" option, on by default.
- A warning when a browser tab is stale after a restart.

**Tested on real projects:**
- **u_bot:** 28 checks passed and 0 failed. The rest wait on owner accounts.
- **model_check:** a small app that reused two library blocks. 11 checks
  passed and 0 failed.

## 0.1, 2026-11-17 to 2026-11-19: first versions

**Foundation:**
- Started as an independent studio, copying the original interface without
  importing the original code.
- Model connections for Claude, Codex and Ollama, with live model lists and
  a Test button.
- Appling can be started in the background, with stop and status scripts.

**How builds are approved and checked:**
- The owner approves the acceptance criteria. QA results are recorded per
  check, and QA can pass in part.
- The owner decides the scope.
- Progress is described in plain language.

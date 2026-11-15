# Appling — Codex edition

Appling is a local project studio for building apps, websites, slide decks and
short videos. This branch runs its coding and agent workflow directly through
[Codex app-server](https://learn.chatgpt.com/docs/app-server).

Current source: **v0.17.13 beta**, branch `codex/appling-codex-base`.

Appling keeps its project UI, previews, owner approvals, project memory and
five-minute status notes. Codex owns execution, native file/terminal tools,
conversation persistence and compaction. Browser QA uses a pinned Playwright CLI and the local preview, with a private
browser session per agent. The shipped Appling runtime does not load Hermes. Historical upstream source remains in this repository for lineage
and rollback; it is excluded from the Appling desktop package.

## Run this branch

Install Python 3.11+, [uv](https://docs.astral.sh/uv/) and Node.js. Install the
pinned Codex CLI and connect the account appropriate for your deployment:

```sh
npm install --global @openai/codex@0.164.0
codex login
npm --prefix apps/appling-browser ci --ignore-scripts
node apps/appling-browser/node_modules/playwright/cli.js install chromium
uv sync --project apps/appling-runtime --locked
apps/appling-runtime/.venv/bin/python -m lyra_lite --no-open --port 9201
```

On Windows, use `apps/appling-runtime/.venv/Scripts/python.exe` for the last
command. Open [Appling Codex](http://127.0.0.1:9201/). To rebuild the UI:

```sh
npm --prefix lyra_lite/ui ci
npm --prefix lyra_lite/ui run build
```

Configuration, the token and project registry live in `~/.appling-codex/`.
`APPLING_HOME` can select an isolated home. Codex owns its credentials and native
sessions; Appling never copies credentials from Hermes. Per-project `.lyra/`
files retain the existing review/history format, with native thread mappings
under `.lyra/codex/`.

## Coding workflow

The selected team and Personal / Reusable / Production profile control scope.
Personal projects use a short plan and coherent feature assignments. Developers
run affected checks during editing, combined checks after integration, then an
independent final QA journey. Existing data integrity and acceptance checks stay
required. Approved requirements remain authoritative; engineering bookkeeping
does not reopen a plan after development starts.

A development lead may launch up to **three** independent coding agents. Each
gets disjoint owned paths in a separate Git worktree. The host checks all touched
files, integrates in a temporary worktree and advances only an unchanged, clean
primary project. Failed or interrupted work is preserved. Shared contracts,
manifests and lockfiles belong to the lead. Native unmanaged subagents are disabled.
Stop interrupts Codex and its child sessions and releases pending owner waits.

## Keep the working version safe

The previous working source is pushed at
[`appling-nice-working-before-codex-2026-11-15`](https://github.com/ub1979/appling/tree/appling-nice-working-before-codex-2026-11-15)
(commit `88fc0f4b3`, “Nice working one”). The original checkout and its service on
port 9200 remain separate. This branch defaults to port 9201 and an empty registry.

Use a **separate project copy** when comparing engines. Never open one project in
two running apps. A legacy project still marked running is rejected. An idle
legacy project gets a private state backup under `.lyra/migrations/before-codex/`
and stays paused until explicit owner input. Messages, queued feedback and approval
hashes are retained. Source rollback alone does not undo project-state migration;
restore the saved state only while both apps are stopped, preserving newer work.

To use the working version again, stop the Codex service and return to the original
checkout. No reset or changes to the original checkout are needed.

## Authentication and distribution

Codex's code is Apache-2.0; the bundle includes its license and notices. Retained
Hermes-derived UI/project utilities keep the repository's MIT attribution.
Model access is governed separately. Existing local/open-source app-server login
is supported for local use. Commercial or hosted distribution must use suitable
API-key access or approved Sign in with ChatGPT; built-in app-server subscription
authentication is not permitted for those services. See the
[official authentication documentation](https://learn.chatgpt.com/docs/app-server#auth-endpoints).
Set `"require_api_key": true` in Appling's `settings.json` to enforce API-key mode.

Optional `.lyra/kit/imagine` uses the OpenAI Images API with `OPENAI_API_KEY` and
paid API credits, only after the owner's agreement. It does not reuse subscription
credentials. Coding, previews and existing templates do not require image generation.

## Validation

See [migration evidence and the regression command](docs/lyra/2026-11-15-codex-migration.md).
Desktop staging uses `apps/appling-runtime/pyproject.toml` and its lockfile rather
than the upstream Hermes Python package. Build with `npm run pack` from
`apps/appling-desktop`; installer CI installs the pinned Codex executable first.

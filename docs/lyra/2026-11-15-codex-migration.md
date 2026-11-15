# Native Codex migration — 2026-11-15

Working base: `88fc0f4b3`, saved and pushed as
`appling-nice-working-before-codex-2026-11-15` (“Nice working one”).
Migration branch: `codex/appling-codex-base`, isolated checkout under `.worktrees/`.

## Runtime boundary

`lyra_lite.engines.codex` uses the installed official Codex app-server over NDJSON
stdio. It passes the workspace, model, stable instructions and dynamic host tools
at thread creation. Thread IDs, pending-turn IDs and token totals are persisted
atomically under the project's `.lyra/codex/` directory. Existing threads resume;
old conversation messages are not replayed. A changed settings/instruction
fingerprint starts a distinct thread with a bounded continuity brief, retaining
the previous thread ID. An uncertain request is never automatically retried.

The four host tools retain concrete Appling capabilities: owner questions/reviews,
role instructions, project recall and controlled delegation. Native file, search,
terminal and compaction behavior belong to Codex. Real browser QA uses the pinned
official Playwright CLI through native terminal commands and the existing preview
host, avoiding the unavailable desktop CUA bridge. No browser model tools are added. Owner command/file permissions
map to explicit once/session/deny decisions, unsupported requests fail closed, and withdrawn
requests close their cards. Stop interrupts the native turn and all managed children.

The packaged runtime contains Appling modules/assets, local browser/media helper
scripts, a small locked Python dependency set, Node/npm, uv, Codex and the pinned Playwright
CLI. Desktop first launch installs Chromium in its own application data directory. It excludes
Hermes' AIAgent, provider/auth/config stack and plugin loader. Historical Hermes
adapters/tests remain in the source tree as previous-engine history, not an engine
option, dependency or fallback in the new product.

## Workflow changes

- One stable development role session carries coherent feature work through its
  own fixes and checks. Only disjoint coding leaves run concurrently.
- The existing worktree ownership, intermediate-commit validation, clean-primary
  and temporary integration guards remain. Stop also blocks integration after
  workers return. Three leaves remain the maximum; failed work is preserved.
- Personal means 1–3 tasks, not a default production process. All profiles retain
  affected checks, a combined integration gate and independent final QA.
- No mandatory full suite after every edit, blanket per-function TDD, class map,
  per-edit change report, research quota or repeated whole-skill loading.
- QA reproduces failures and separates harness errors from product bugs; two
  unsuccessful attempts at one hypothesis require new evidence or a revised one.
- Full child reports are saved to files. Inline reports have a fixed generous
  ceiling and a full-report path, never a limit derived from lifetime billed tokens.
  The inherited Hermes summary-budget/LSP write paths are not used by this runtime.
- Existing five-minute status notes remain display-only. Nested worker identities
  are preserved; quiet tools alone do not imply an AI outage or a stalled job.

## Rollback and project state

The original checkout, port 9200 and ~/.hermes are unchanged. New instances use
~/.appling-codex and port 9201. No existing project registry is imported automatically.
An idle legacy project is backed up and paused; running legacy projects are refused.
For comparisons, copy the project and its state first. Do not run both engines on
one folder. Restore legacy state only while both apps are stopped, keeping newer
feedback and work in a separate backup. Do not use a destructive reset to roll back.

## Evidence

- Installed Codex CLI 0.164.0 accepted native thread creation, dynamic tools,
  permissions, model selection and model discovery.
- A real coding turn created two Python files and ran two unittest cases in 13.4s.
- Two real coding leaves ran concurrently in separate Git worktrees, verified
  arithmetic cases, and integrated to a clean primary in 19.3s. Combined checks
  are still required after any integration; merge success alone is not acceptance.
- A fresh standalone Python environment served the UI, settings, engine catalog,
  projects and all 35 templates with every Hermes runtime import blocked.
- Real HTTP/SSE regression tests use an executable app-server peer over real pipes,
  including Stop during a permission wait and review recovery after daemon restart.
- A real guided counter project progressed through prototype, requirements,
  implementation-plan approval, development and independent QA, preserving saved
  context across restart. Unavailable browser checks were reported as unverified
  rather than announcing readiness; the browser path was then supplied explicitly.
- Real Codex-driven Playwright QA then passed zero/increment/decrement/negative/Reset,
  keyboard focus and Enter/Space, reload-to-zero, 320px overflow, and no external
  network requests in Chromium 158.0.8127.18. Browser sessions were closed afterward.
- These are small smoke tests, not a claim that a twelve-hour project now has a
  guaranteed completion time. Model, project complexity, browser availability and
  genuine dependencies still affect speed.

Final supported regression matrix: **211 backend checks**, **40 UI checks**, and a
successful TypeScript/production UI build, plus 9 release/version checks. Static undefined/unused-name checks and
the standalone staged-package smoke also passed. Native coding, concurrent workers
and browser QA were exercised separately as described above.

Run the supported Codex regression matrix from this checkout:

```sh
scripts/run_tests.sh -j 4 \
  tests/lyra_lite/test_codex_engine.py \
  tests/lyra_lite/test_codex_daemon.py \
  tests/lyra_lite/test_codex_runtime.py \
  tests/lyra_lite/test_development_worktrees.py \
  tests/lyra_lite/test_status_updates.py \
  tests/lyra_lite/test_watchdog.py \
  tests/lyra_lite/test_plan_execution_review.py \
  tests/lyra_lite/test_review_lifecycle.py \
  tests/lyra_lite/test_requirements_approval.py \
  tests/lyra_lite/test_project_archive.py \
  tests/lyra_lite/test_project_map.py \
  tests/lyra_lite/test_project_memory.py \
  tests/lyra_lite/test_transcript.py \
  tests/lyra_lite/test_chat_answers.py \
  tests/lyra_lite/test_checker_sync.py \
  tests/lyra_lite/test_folder_picker.py
npm --prefix lyra_lite/ui test
npm --prefix lyra_lite/ui run build
```

Native Windows/Linux installers were not built in this macOS run; the pinned
packaging paths and standalone staged runtime were checked locally.

Legacy Hermes fake-provider tests exercise the retired engine, not the new Codex
protocol. They are not claimed as Codex integration coverage.

Authentication: local usage may use the user's Codex sign-in; commercial/hosted
service deployments need appropriate API-key access or approved Sign in with ChatGPT.
The setting `require_api_key` rejects subscription-mode execution for those deployments.

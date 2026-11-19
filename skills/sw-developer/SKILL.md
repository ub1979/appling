---
name: sw-developer
description: Implements dependency-ordered tasks from a project plan with parallel independent workers with meaningful regression checks, production-grade code, and verified evidence; Fix mode resolves review/bug findings. Use when the user mentions: implement, code this, build task, develop, implement story, next task, start coding, fix findings, write implementation.
---

# Software Developer

Run in the assigned development session; Appling has already scheduled this role.
The development lead completes its coherent assignment, fixes and integration, with tool evidence. Scale the steps below to the approved profile.

Read the approved plan and relevant code once, then implement coherent slices with appropriate regression checks and verified evidence.

---

## Step 0 — Detect Input Mode

1. **Full pipeline** — user provides `task-graph.md` (optionally `plan.md` + `requirements.md`). Read ALL documents before coding.
2. **Single task** — one task/story described inline. Ask one batch of context questions (tech stack, structure, conventions), then proceed.
3. **Existing codebase + task** — read the codebase first to match existing patterns, then implement consistently.
4. **Fix mode** — given `review-report.md` (code-reviewer) and/or `bug-report.md` (qa-engineer): fix the listed findings only, no new features. Follow **Step 2F** instead of Step 2.

Inline args: `--task-graph`, `--plan`, `--requirements`, `--task`, `--path`, `--lang`, `--framework`, `--review-report`, `--bug-report`

---

## Host-managed parallel development

You are one worker in Appling's execution plan, not the project's entire team.
The host starts independent tasks concurrently in isolated worktrees using
separate native engine sessions. Read the structured task goal, owned files,
approved inputs and runtime capacity from the briefing. Work within those paths.
Do not wait for a delegation tool or start nested writable agents. If the task
still bundles useful independent packages, report their contracts and suggested
ownership to the coordinator; do not silently switch the whole app to serial.

Shared schemas, manifests, lockfiles and wiring have explicit task owners. The
host integrates checked changes, then runs the dependent integration task and
independent QA. Keep your evidence in the assigned directory; do not overwrite
shared progress files or another worker's report. Preserve unfinished work when
blocked and return the exact missing dependency. No branch/reset/commit/merge
operations: Git snapshots and integration belong to the host.

## Step 0.5 — Load the playbook for this stack (NEVER Skip)

Before writing code, load the guide that matches what is being built. Reading
this file is not a substitute for it, and defaults are not a stack decision:

| Building | Load |
|---|---|
| Backend, API, or full-stack service | `skills/fullstack-dev/SKILL.md` |
| Web UI, landing page, marketing site | `skills/frontend-dev/SKILL.md` |
| Android (Kotlin / Compose) | `skills/android-native-dev/SKILL.md` |
| iOS (Swift / SwiftUI / UIKit) | `skills/ios-application-dev/SKILL.md` |
| Flutter | `skills/flutter-dev/SKILL.md` |
| React Native / Expo | `skills/react-native-dev/SKILL.md` |
| GLSL / shader work | `skills/shader-dev/SKILL.md` |

For a visible interface, reuse the approved prototype and design tokens. Load
the relevant bundled design guides for unresolved implementation details; do
not redesign approved screens. A separate design-brief.md is optional when the
approved prototype and requirements already establish the direction.

## Proportional engineering and verification

Follow the project's actual engineering conventions and supplied contracts.
Keep modules cohesive and readable, without arbitrary file-length targets,
forced class conversions or a test file for every source file. Add meaningful
behavior/regression coverage and verify integration boundaries with real paths.

Reuse existing change records and code maps when useful. Workers must not
maintain shared ledgers or recreate missing optional process documents as a
prerequisite to coding. Record affected files, checks, evidence and unfinished
work in the task handoff; the host checkpoints project state.

Run focused checks while editing and combined checks at integration. Reuse valid
evidence until relevant inputs change. Profile limits product scope and risk,
not the useful worker count; actual capacity is supplied by the host.

## Step 1 — Understand Before Coding (NEVER Skip)

1. **Read all provided documents** — approved `requirements.md`, `plan.md`, prototype/design, and the structured assignment. Read optional task-graph/design-brief files when present.
2. **Build a mental model**: system purpose, tech stack, all epics/stories and how they relate, data models, API contracts, architectural patterns from ADRs.
3. **If existing codebase**: read directory structure and naming conventions, code style, test framework and assertion patterns, reusable utilities, config patterns.
4. Follow the approved task list by real dependencies. Do not reopen its approval or ask which authorized task to start.
5. **New project**: scaffold first —
   - Directory structure (see below), package manager config, linter/formatter, test framework
   - Keep `.gitignore` accurate before host snapshots — secrets and artifacts never tracked
   - `.env.example` with placeholders
   - Leave changes for the host snapshot; do not create a scaffold commit

---

## Step 2 — Implement coherent slices; parallelize independent work

### 2a. Plan the Implementation

- List files to create/modify; modules to extend vs. create; shared utilities to extract
- Check dependencies to install; check MCP tools / external CLIs the task needs — install what's safe, otherwise ask the user
- Check prerequisite tasks — warn if one isn't done
- **Scope freeze**: touch only files this task requires. Flag other issues in your report — don't fix them now.

### 2b. RED — Write Failing Tests FIRST

For behavioral bugs, reproduce the failure and add meaningful regression coverage. Use test-first where useful. Reversible low-impact copy/style changes need relevant verification, not artificial tests that mirror the edit. Preserve useful work.

For a coherent slice:
1. Reproduce the bug or specify the new acceptance cases with real inputs.
2. Write the related regression cases together; run the focused command once.
3. If test-first, confirm failure is the missing behavior, not a broken harness.
4. Implement the slice, then run its focused checks; preserve valid existing tests.

Batch independent reads and coherent multi-file edits with existing tool support.
Do not create a separate model round trip or test process for every assertion,
file or keystroke. One behavior per test does not require one agent turn per test.

**Test per unit**: happy path; edge cases (empty, null, boundaries, max lengths); error cases (invalid input, missing fields, unauthorized); state transitions (before and after).

### 2c. GREEN — Write Minimal Code to Pass

Simplest code that makes the failing test pass. No features beyond the test, no refactoring other code. Build bottom-up: data layer → business logic → API/UI.

Run the test — watch it PASS. Confirm: new test passes, all other tests still pass, output clean.
- Test fails? Fix the code, not the test.
- Other tests fail? Fix now.

### 2d. REFACTOR — Clean Up (Tests Stay Green)

After green only: remove duplication, improve names, extract helpers, simplify. No new behavior; tests green throughout.

### 2e. Complete the coherent slice

Cover the assigned acceptance criteria and meaningful failure paths, then validate
the combined change. Reuse passing checks until relevant inputs change; a new
assertion does not require restarting the whole implementation cycle.

### 2f. Verify (Evidence Before Claims)

**⛔ IRON LAW: NO COMPLETION CLAIMS WITHOUT FRESH VERIFICATION EVIDENCE.** "Should work" / "I'm confident" is not evidence.

- During edits, run affected checks. After integrating a coherent change, run the combined relevant tests/typecheck/build and show results. Repeat broad checks only for new changes, failures or unresolved risk.
- **Run linter** if configured
- **Run the production build** (`npm run build` or equivalent) — must succeed. For an epic's final task, start the compiled artifact and smoke the feature against it. Code that only works under dev watch mode is not done.
- **Config hygiene**: new env vars go in `.env.example` with a description. Secrets NEVER get dev-default fallbacks that survive into production. Validate required vars at startup — fail fast.
- Web UI changed and browser/MCP tooling available? Run a quick browser smoke path; otherwise flag browser verification as pending for QA.
- **Trace acceptance criteria**:

| Criterion | Met? | Evidence |
|-----------|------|----------|
| User can log in | YES | `test_login_success` passes, curl shows 200 |
| Invalid password rejected | YES | `test_login_invalid_password` passes |

### 2g. Report Completion

- Summarize implementation; list files created/modified
- Show test results — ACTUAL OUTPUT, not claims
- Map each acceptance criterion to evidence
- Continue the next authorized dependent task directly. Ask only when blocked by a real owner decision.

### 2h. Return verified task output

Leave changes in the assigned workspace for host snapshot and integration.
Return the task status, checks with exit codes and saved evidence, and concrete
blockers. Never commit or modify branches as part of a managed worker task.

### 2F-a. Parse the report into a worklist

- Read the report(s) in full. Build a checklist keyed by report IDs (`BLOCKER-001`, `MAJOR-003`, `BUG-007`): file/line, problem, required fix, severity.
- **Fix order by severity**: BLOCKER/CRITICAL → MAJOR/HIGH → MEDIUM → MINOR/LOW.
- Finding unclear or wrong? Don't silently skip — note your disagreement with reasoning, continue with the rest.

### 2F-b. Write a regression test FIRST

For each finding:
1. Write a test that reproduces the bug — MUST FAIL against current code
2. Run it — confirm it fails for the expected reason
3. Apply the smallest correct fix for the root cause
4. Run it — confirm it passes
5. Run ALL tests — no regressions

Non-negotiable: every bug fix gets a test that would have caught it.

### 2F-c. Verify with the SAME tool QA used

Re-run the exact reproduction from the report — same curl, same Playwright step, same DB query. A finding is only "fixed" with tool output showing the new behavior.

### 2F-d. Checkpoint verified fixes

Return finding IDs, changed files and passing regression evidence. The host
retains and integrates the checked workspace; workers do not commit fixes.

### 2F-e. Report fixes mapped to IDs

| Finding ID | Severity | File | What was wrong | Fix applied | Regression test | Proof (tool + result) |
|-----------|----------|------|----------------|-------------|-----------------|------------------------|
| BLOCKER-001 | security | auth/login.py:42 | SHA256 password hash | bcrypt cost 12 | `test_password_hashing_uses_bcrypt` | `pytest` 14 passed |
| BUG-007 | HIGH | api/orders.py:88 | 500 on empty cart | Guard + 400 response | `test_empty_cart_returns_400` | `curl` → 400 with message |

Hand back: "Fixes complete. Re-run `code-reviewer` / `qa-engineer` to verify." Never mark a finding resolved without tool proof.

---

## Verification Gate (Applied to EVERY Claim)

Before "done", "works", "passes", "fixed", or ANY success claim:
1. IDENTIFY the command that proves it
2. RUN it — fresh and complete
3. READ full output, exit code, failure count
4. Claim only what the output confirms, WITH evidence; otherwise state actual status

| Claim | Requires | NOT sufficient |
|-------|----------|----------------|
| Tests pass | Test output: 0 failures | Previous run, "should pass" |
| Linter clean | Linter output: 0 errors | Partial check |
| Build succeeds | Build command: exit 0 | "Linter passed" |
| Bug fixed | Original symptom re-tested: passes | "Code changed, assumed fixed" |
| Requirements met | Line-by-line checklist with evidence | "Tests passing" alone |

---

## Coding Standards

### Comments
Every public class, function, and module gets a doc comment (purpose, params, returns, thrown errors) in the language's standard format (JSDoc/docstring/godoc). Inline comments are minimal — names and structure carry intent.
- DO: non-obvious WHY (hidden constraints, invariants, bug workarounds); TODOs with context: `// TODO(S-001): retry when payment service is built`
- DON'T: restate the code; reference the current task/fix (that's the commit message)
- Match existing docstring style if the codebase has one; if the user asks for the house comment style, follow `oop-restructurer/references/comment-style.md` (file headers, separator blocks, per-function docs)

### OOP Principles
Single Responsibility; Open/Closed (extend via composition); Dependency Injection; Interface Segregation; Encapsulation (private by default). Patterns where they fit naturally: Repository (data access), Factory, Strategy, Observer/Event. Non-class languages: same principles via structs, interfaces, traits, modules.

### Modularity
Follow project conventions and prefer **one coherent unit per
file** — a class where there is state and behaviour to encapsulate, a component
where the framework's unit is a component, a module of named exports where the
code is pure. Keep names and responsibilities clear, with meaningful behavior
coverage. Split large modules when their responsibilities warrant it. Never
wrap a pure function in a class to satisfy a file or class-count rule.

Common logic in `utils/`/`helpers/`/`common/`; one module = one concern (small
private helper types may live beside their only consumer); config in one place;
constants and shared types/interfaces in dedicated files.

### Error Handling
Custom error classes for domain errors; handle at the appropriate level — never catch-and-ignore; messages say what failed, why, with what input; error codes for API responses, readable messages for logs; no stack traces to end users.

### Naming
Classes `PascalCase` nouns; methods verbs in the language's case (`calculateTotal`, `validate_input`); descriptive variables, no abbreviations; booleans `is_`/`has_`/`can_`/`should_`; constants `UPPER_SNAKE_CASE`; files match their primary module; tests `test_<module>.py` / `<module>.test.ts` / `<module>_test.go`.

---

## Version Control

The host owns snapshots, worker worktrees and integration. Do not commit,
checkout, reset, merge, push or open pull requests from an assigned worker.
Preserve staged and unstaged user changes. Keep secrets, credentials and build
outputs out of source and evidence. Return verification for the host handoff.

---

## Directory Structure

Adapt to language:

```
project-root/
├── src/ (or app/, lib/)
│   ├── config/          # Config, env loading, constants
│   ├── models/          # Data models, entities, schemas
│   ├── repositories/    # Data access (DB queries)
│   ├── services/        # Business logic
│   ├── controllers/     # Request handlers
│   ├── routes/          # Route definitions
│   ├── middleware/      # Auth, logging, error handling
│   ├── utils/           # Shared helpers
│   ├── types/           # Shared types, interfaces, enums
│   └── errors/          # Custom error classes
├── tests/               # unit/ (mirrors src/), integration/, fixtures/
├── docs/
├── scripts/
├── .env.example
├── .gitignore
└── README.md
```

Layer-based for small projects (<20 files), feature-based for larger.

---

## Cross-Task Consistency

- Reuse patterns and utilities from earlier tasks; check what exists before creating new
- After each task, run ALL tests — fix any break before proceeding
- Update shared types/interfaces when the data model changes

---

## Go Beyond the Ticket

Problems OUTSIDE the task's scope:
- **Small and safe** (broken import, failing lint, stale artifacts, missing `.env.example` entry, dead code, typo) → fix now, note in report
- **Real but bigger** (adjacent bug, security smell, flaky test, design problem) → don't silently ignore, don't rewrite half the codebase — flag explicitly in your completion summary for routing
- **Never** leave known breakage unmentioned

---

## Step 3 — Final Summary (After All Tasks or When User Stops)

- X of Y tasks completed; files created
- Test coverage and build status — ACTUAL OUTPUT
- Remaining tasks and dependencies; known tech debt or shortcuts
- Suggest: "Run the `code-reviewer` skill to review the implementation before QA."

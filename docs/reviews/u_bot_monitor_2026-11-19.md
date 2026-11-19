# u_bot monitoring — 19 November 2026

Continued using retrieved history from the same-project chat **Analyse Appling Folder**, the live browser, and read-only controller records. The retrieved history is a summary, not the full transcript. Preserve the approved implementation, controller approval gates, retained workspaces and completed integrations. No project replanning, approval changes or manual worker/task status changes were performed.

## Observed execution

At 00:31–00:33 UTC the controller was in build, running and unpaused. Contracts, WhatsApp and data were integrated. Browser, speech and UI workers were running in retained isolated workspaces. New tool events and changed files showed ongoing activity; this was not inferred solely from the UI's working label. All three current approved artifact hashes matched their files. Integration and independent QA were still pending.

The browser worker was repairing a scoped meeting-transport test that ended with an unresolved promise. This was not counted as passing. The speech worker retained a local synthetic throughput report, but native capture/output acceptance was blocked by absent BlackHole, absent capture permission and absent remote-participant receipts. Its installer had previously failed signature validation. No driver installation, OS permission request or real meeting action was attempted in this check.

Browser evidence: ../evidence/u_bot-monitor-2026-11-19.jpg. This records the active studio, not successful generated-app QA.

## Fresh validation

| Check | Result |
|---|---|
| Appling `.venv/bin/python -m pytest tests` | 161 passed; one Starlette/httpx deprecation warning |
| Appling `cd ui && npm test && npm run build` | 58 passed; TypeScript and production build passed; bundle size warning |
| u_bot typecheck, lint, production build | Passed using the existing repository-local Node 24 runtime |
| Combined u_bot contracts/core/data/providers/WhatsApp suites | 68 passed, 2 failed: HTTP and Ollama transport fixtures could not listen on localhost (`EPERM`) |
| u_bot application on port 4317 | Browser connection refused before launch; `npm start` then exited 1 and could not open the server |

The shell's default Anaconda `python -m pytest tests` exited 139 without output. The repository virtual environment was then used for the complete passing backend run. Tests did not establish a clean default-Python environment.

The exact combined u_bot test command was `node --experimental-strip-types --test tests/contracts/*.test.ts tests/core/*.test.ts tests/data/*.test.ts tests/providers/*.test.ts tests/whatsapp/*.test.ts`. Its full result remains failed; passing subsets are not substitutes. Local listener restrictions prevented fresh generated-app browser QA. No passing UI QA, authenticated accounts, provider-driven full workflow, meeting delivery, five-day briefing acceptance or project completion is claimed.

Appling remains running at http://127.0.0.1:9210/#/p/2a2446b9bab2 with its existing workers. The generated u_bot application was not successfully started by this session. A normal host launch is required for port 4317; the observed failure must not be treated as evidence that the port was occupied.

## Parallel execution audit — 00:36 UTC

The live run demonstrates real concurrent execution, not just a planned graph. Browser, speech and UI each started a distinct model invocation at 00:29:22 and generated interleaved activity through 00:35. They have distinct persisted Codex thread IDs, separate retained worktree directories and mutually disjoint assigned file scopes. Effective project capacity is three workers. The resolved engine reports gpt-6.1-sol with medium effort.

Rolling refill is verified in actual project history: data integrated at 00:16:37; UI started at 00:16:38 while browser and speech remained running until the owner stop at 00:22:36. This proves the running service does not wait for the entire wave before refilling a free slot. It does not measure speedup against a sequential baseline.

Managed workers explicitly disable `features.multi_agent` and `features.multi_agent_v2` in appling/engines/codex.py. The swarm is Appling's three independently controlled Codex workers; recursive native Codex subagents are not enabled. There were zero native-child events in the current turn. The scheduler uses FIRST_COMPLETED, integrates through one controller, and recomputes eligibility subject to dependencies, capacity and active file ownership. Independent QA is assigned qa-engineer with verification kind after integration; it has not run yet. Approved prototype, requirements and plan hashes still match.

At 00:36 the speech worker had returned blocked and its task was pending, preserving its implementation rather than marking it done. Its fresh reported synthetic timing is 183.885 seconds for 600 seconds of ASR input and 0.248 seconds for warm 25-word TTS. Those measurements do not establish real meeting capture/output. BlackHole, trusted installation, capture permission and participant acceptance remain blocking. Browser and UI were still running. No other task was eligible alongside them, even with spare capacity: productivity/social/workflows require browser, briefings requires productivity, meetings requires browser and speech, integration requires the feature tasks, and QA requires integration.

The browser worker's 00:35:04 transport-socket-diagnosis.log contains a concrete failed local-fixture assertion: received frames included `unapproved-chat`, where only `fixture-signal` was expected. Earlier attempts also timed out. The worker was still investigating; this evidence does not establish its final root cause or a fixed guard. It involved a disposable local fixture, not a real account. Browser work has not been integrated as completed. UI's fresh acceptance log showed nine passing tests with fixture-browser evidence, which is not final integrated-app QA.

Assessment: bounded parallel orchestration and rolling refill are functioning. The full application is not yet working to approved acceptance. Browser guard repair and native-audio prerequisites are current bottlenecks; additional worker capacity alone would not unlock another ready task at this checkpoint. No live configuration or application code was changed by this audit.

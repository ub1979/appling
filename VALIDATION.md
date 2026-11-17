# Validation

## Automated coverage

Latest local result: **32 backend tests passed; 42 frontend tests passed**.
TypeScript checks and the Vite production build passed. The stylesheet was
retained byte-for-byte from the original interface.

- Backend behavior checks exercise the complete controller flow with temporary
  project files, revision-bound approvals, task dependencies, memory isolation,
  interruption/restart, follow-up changes, API authentication and settings.
- Launcher checks cover occupied-port fallback, strict explicit ports, permission
  failures, and keeping the browser URL aligned with the reserved server socket.
- Subprocess protocol checks exercise Codex initialization, thread resume,
  approvals, questions, task completion and usage notifications through a real
  child process implementing the protocol.
- Claude/Copilot adapter checks exercise structured events, permission gating,
  command flags and process completion through controlled child processes.
- HTTP adapter checks exercise Ollama/OpenAI-format tool calls and actual file
  writes, Anthropic Messages requests, stable session prefixes, interrupted
  exchange recovery and context compression using controlled HTTP transports.
- The preserved frontend's behavior tests, TypeScript checks and Vite production
  build run independently from the original checkout.

## Installed runtime check

The installed Codex CLI (0.164.0) successfully answered an app-server initialize
request using a disposable Codex home. No model call or paid work was requested
by this check. CLI installation is not proof of login or model entitlement.

## Environment limitations

The backend initialized successfully, but this execution environment denied
binding `127.0.0.1:9210`. Consequently a live browser walkthrough of the new
studio was not performed. Browser automation installation was also unavailable
from the offline package cache; `scripts/setup-browser.sh` provides the normal
installation path.

Authenticated real-model generation through Codex, Claude Code, Copilot, Ollama
and API providers has not been verified here. Protocol and controlled-transport
tests establish integration behavior, not model output quality or a speedup.

## Live acceptance run

On a machine with localhost access and the selected engine authenticated:

1. Launch with `./start.sh`, choose the engine/model in Settings, and create a
   simple counter application in a disposable project folder.
2. Complete the interview. Open and approve the clickable prototype, then the
   requirements and plan. Confirm implementation did not start before approval.
3. Allow build/test commands, inspect the browser evidence and try the built app.
4. Request an in-scope fix and confirm it reuses approved requirements.
5. Add a materially new feature and confirm it receives a focused requirements
   update. Modify a reviewed artifact and confirm stale approval is rejected.
6. Stop/restart during work, switch the development connection, and confirm task
   checkpoints and earlier user decisions remain available.
7. Repeat with each intended connection before treating it as release-verified.

The first implementation is suitable for these local acceptance checks; it is
not represented as a production-validated release.

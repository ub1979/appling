"""Bounded development fan-out with separate Git indexes and checked integration.

Worktrees prevent accidental concurrent edits; they are not a filesystem sandbox.
The original project is advanced only after the whole wave passes validation.
"""

from __future__ import annotations

import json
import subprocess
import threading
import uuid
from pathlib import Path, PurePosixPath

from lyra_lite.agents import agent_for_goal


RESERVED = {"package.json", "package-lock.json", "npm-shrinkwrap.json", "pnpm-lock.yaml",
            "yarn.lock", "pyproject.toml", "uv.lock", "requirements.md", "plan.md", "task-graph.md"}


def git(root: Path, *args: str) -> str:
    result = subprocess.run(["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60)
    if result.returncode:
        raise ValueError((result.stderr or result.stdout).strip()[-2000:])
    return result.stdout.strip()


def _paths(value) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError("Each coding task needs nonempty owned_paths in its JSON context.")
    paths = []
    for raw in value:
        if not isinstance(raw, str) or not raw.strip():
            raise ValueError("Owned paths must be project-relative files or directories.")
        path = PurePosixPath(raw.rstrip("/"))
        if (path.is_absolute() or not path.parts or any(p in {".", "..", ".git", ".lyra", ".sdlc"} for p in raw.rstrip("/").split("/"))
                or any(c in raw for c in ":\\*?[]\x00\n\r") or path.as_posix() in RESERVED):
            raise ValueError(f"Unsafe or lead-owned path: {raw!r}")
        paths.append(path.as_posix())
    return paths


def _overlap(a: str, b: str) -> bool:
    # Use portable ownership even when the current filesystem is case-sensitive.
    a, b = a.casefold(), b.casefold()
    return a == b or a.startswith(b + "/") or b.startswith(a + "/")


def _owns(path: str, owned: list[str]) -> bool:
    return any(path == p or path.startswith(p + "/") for p in owned)


class DevelopmentWave:
    def __init__(self, root: Path, max_workers: int = 10):
        self.root = root.resolve()
        self.max_workers = max_workers
        self.lock = threading.Lock()

    def dispatch(self, parent, args: dict, executor=None) -> str:
        if not self.lock.acquire(blocking=False):
            return json.dumps({"error": "A development wave is already running for this lead."})
        wave = None
        result = {}
        try:
            if executor is None:
                from tools.delegate_tool import delegate_task, _get_max_concurrent_children
                limit = min(self.max_workers, _get_max_concurrent_children(parent))
            else:
                limit = self.max_workers

            tasks = args.get("tasks")
            if isinstance(tasks, str):
                tasks = json.loads(tasks)
            if not tasks:
                tasks = [{"goal": args.get("goal"), "context": args.get("context")}]
            if not isinstance(tasks, list) or not 1 <= len(tasks) <= limit:
                raise ValueError(f"Use 1–{limit} independent coding tasks per wave.")
            owned = []
            instructions = []
            for task in tasks:
                if not isinstance(task, dict) or not isinstance(task.get("goal"), str) or not task["goal"].strip():
                    raise ValueError("Each coding task needs a goal.")
                context = task.get("context")
                context = json.loads(context) if isinstance(context, str) else context
                if not isinstance(context, dict):
                    raise ValueError("Task context must be JSON with owned_paths and instructions.")
                read_only = context.get("read_only") is True
                paths = [] if read_only else _paths(context.get("owned_paths"))
                if any(_overlap(a, b) for previous in owned for a in paths for b in previous):
                    raise ValueError("Coding tasks have overlapping file ownership; combine them or run serially.")
                if any(not (self.root / path).resolve().is_relative_to(self.root) for path in paths):
                    raise ValueError("Owned paths cannot resolve outside the project.")
                owned.append(paths)
                instructions.append(str(context.get("instructions") or ""))
            base = git(self.root, "rev-parse", "HEAD")
            if Path(git(self.root, "rev-parse", "--show-toplevel")).resolve() != self.root:
                raise ValueError("Parallel coding needs a Git repository rooted at this project. Work serially here.")
            branch = git(self.root, "symbolic-ref", "--short", "HEAD")
            if git(self.root, "status", "--porcelain"):
                raise ValueError("Checkpoint the primary project's changes before starting parallel work.")
            wave = self.root / ".lyra" / "development" / uuid.uuid4().hex[:12]
            wave.mkdir(parents=True)
            # ProjectStore ignores .lyra, so the worktree guard stays clean.
            records = []
            prepared = []
            for index, task in enumerate(tasks):
                name = f"appling/dev-{wave.name}-{index}"
                path = wave / f"worker-{index}"
                git(self.root, "worktree", "add", "-b", name, str(path), base)
                records.append({"workspace": str(path), "branch": name, "owned_paths": owned[index],
                                "read_only": not bool(owned[index])})
                prepared.append({"goal": task["goal"], "role": "leaf", "context": (
                    f"Assigned workspace: {path}; baseline commit: {base}. Use this directory for ALL file and terminal operations. "
                    f"The primary project at {self.root} is read-only to you. "
                    f"Exclusive writable paths: {json.dumps(owned[index])}; an empty list means read-only analysis/QA. "
                    "Do not edit any other paths or shared contracts/config/lockfiles/Project Brain. "
                    "Do not switch branches, merge, push, reset or touch other worktrees. "
                    "Perform only your assigned role's work. Read-only workers must not edit source or shared reports; "
                    "use temporary directories for test data and artifacts. Report exact checks/results and remaining work. "
                    "The host will save and integrate the work after every worker finishes.\n" + instructions[index]
                )})
            metadata = {"base": base, "branch": branch, "workers": records}
            (wave / "wave.json").write_text(json.dumps(metadata, indent=2) + "\n")
            if executor is None:
                raw = delegate_task(tasks=prepared, parent_agent=parent, background=False,
                                    task_runtimes=[{"workspace": r["workspace"]} for r in records])
            else:
                raw = executor(prepared, records)
            result = json.loads(raw)
            (wave / "result.json").write_text(json.dumps(result, indent=2) + "\n")
            results = result.get("results") or []
            if (len(results) != len(records) or any(r.get("status") != "completed"
                    or r.get("exit_reason") != "completed" for r in results)
                    or getattr(parent, "_interrupt_requested", False)):
                raise ValueError("A worker did not finish successfully. The primary project was not integrated.")
            self.integrate(wave, metadata)
            return json.dumps({**result, "integration": ("read-only results validated against the saved baseline" if all(r.get("read_only") for r in records)
                                               else "merged; combined validation is still required"),
                               "recovery": str(wave), "workers": records, "baseline": base,
                               "checks_require_rerun": any(r.get("read_only") for r in records) and any(not r.get("read_only") for r in records)})
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return json.dumps({**result, "error": str(exc), "recovery": str(wave) if wave else None,
                               "next": "Inspect preserved work and resolve serially; do not bypass the integration guard."})
        finally:
            self.lock.release()

    def integrate(self, wave: Path, metadata: dict) -> None:
        base = metadata["base"]
        for record in metadata["workers"]:
            path = Path(record["workspace"])
            if git(path, "symbolic-ref", "--short", "HEAD") != record["branch"]:
                raise ValueError("A worker changed its assigned branch; integration blocked.")
            git(path, "merge-base", "--is-ancestor", base, "HEAD")
            changed = set(filter(None, git(path, "diff", "--name-only", "--no-renames", "-z", base).split("\x00")))
            changed.update(filter(None, git(path, "diff", "--cached", "--name-only", "--no-renames", "-z", base).split("\x00")))
            changed.update(filter(None, git(path, "ls-files", "--others", "--exclude-standard", "-z").split("\x00")))
            # Inspect intermediate commits too: a final revert must not sneak
            # an unowned file (or secret) into the integrated Git history.
            historical = set(filter(None, git(path, "log", "--format=", "--name-only", "--no-renames", "-z", f"{base}..HEAD").split("\x00")))
            touched = changed | {p.lstrip("\n") for p in historical}
            if record.get("read_only") and touched:
                raise ValueError("A read-only worker modified source; its result was rejected and work preserved.")
            if any(not _owns(p, record["owned_paths"]) for p in touched):
                raise ValueError("A worker changed files outside its ownership; integration blocked.")
            if touched:
                _paths(list(touched))
            if any(not (path / p).resolve().is_relative_to(path) for p in changed):
                raise ValueError("A worker created a path outside its worktree; integration blocked.")
            if git(path, "status", "--porcelain"):
                # Validated paths only; separate worktrees have separate indexes.
                dirty = set(filter(None, git(path, "diff", "HEAD", "--name-only", "--no-renames", "-z").split("\x00")))
                dirty.update(filter(None, git(path, "diff", "--cached", "--name-only", "--no-renames", "-z").split("\x00")))
                dirty.update(filter(None, git(path, "ls-files", "--others", "--exclude-standard", "-z").split("\x00")))
                if any(not _owns(p, record["owned_paths"]) for p in dirty):
                    raise ValueError("Unowned working changes in a worker; integration blocked.")
                git(path, "add", "-A", "--", *sorted(dirty))
                git(path, "commit", "-m", "Implement isolated Appling coding task")
            record["commit"] = git(path, "rev-parse", "HEAD")
        if all(record.get("read_only") for record in metadata["workers"]):
            if (git(self.root, "rev-parse", "HEAD") != base
                    or git(self.root, "symbolic-ref", "--short", "HEAD") != metadata["branch"]
                    or git(self.root, "status", "--porcelain")):
                raise ValueError("The primary project changed; these checks apply only to the saved baseline, not the current app.")
            metadata["validated_baseline"] = base
            (wave / "wave.json").write_text(json.dumps(metadata, indent=2) + "\n")
            for record in metadata["workers"]:
                git(self.root, "worktree", "remove", record["workspace"])
            return
        integration = wave / "integration"
        name = f"appling/integrate-{wave.name}"
        git(self.root, "worktree", "add", "-b", name, str(integration), base)
        for record in metadata["workers"]:
            try:
                git(integration, "merge", "--no-ff", "--no-edit", record["commit"])
            except ValueError:
                git(integration, "merge", "--abort")
                raise ValueError("Integration conflict in the temporary worktree; original project unchanged.") from None
        if (git(self.root, "symbolic-ref", "--short", "HEAD") != metadata["branch"]
                or git(self.root, "rev-parse", "HEAD") != base or git(self.root, "status", "--porcelain")):
            raise ValueError("The primary project changed during this wave; automatic integration blocked.")
        git(self.root, "merge", "--ff-only", name)
        metadata["integrated"] = git(self.root, "rev-parse", "HEAD")
        (wave / "wave.json").write_text(json.dumps(metadata, indent=2) + "\n")
        # Keep branch commits and the wave report for recovery. Remove only
        # clean worktree checkouts, never force-remove a failed worker's files.
        for path in [*[Path(r["workspace"]) for r in metadata["workers"]], integration]:
            try:
                git(self.root, "worktree", "remove", str(path))
            except ValueError:
                pass


# Only approved roles with useful independent work receive leaf helpers. The
# interactive requirements interview and shared planning remain single-owner.
PARALLEL_ROLES = frozenset({"sw-developer", "website-builder", "oop-restructurer", "debugger",
    "researcher", "sw-architect", "code-reviewer", "qa-engineer", "a11y-auditor",
    "security-auditor", "tech-writer", "ux-writer", "benchmark", "health", "devops-engineer"})

ROLE_CONTEXT = """
Stay within the assigned role and approved team. Own the whole coherent assignment,
including fixes and integration; do not hand back after every tiny task. Parallelize
only independent work with stable interfaces and explain the chosen count and why
it helps before dispatch. Put that one-sentence rationale in the batch's top-level
context. The shared process-wide budget defaults to 10 executing
role leads plus workers, configurable to 15; your own lead occupies one slot.
Fewer independent tasks, provider limits or shared dependencies justify fewer.
Do small/dependent work directly. If capacity is unavailable, continue useful work
directly or wait for existing results; do not repeatedly retry delegation.

Every leaf task context is JSON: {"read_only":true,"instructions":"focused check"}
for analysis/research/QA, or {"owned_paths":["src/feature/","tests/feature/"],
"instructions":"contract, acceptance criteria, affected check commands"} for edits.
The same role/model/provider is inherited; helpers do not activate unselected roles.
Requirements interviews, architecture decisions, shared contracts, manifests,
lockfiles, plan/progress and Project Brain stay with their responsible lead.
Checkpoint a clean project-root Git repository before a wave. Each leaf receives
an isolated worktree at the same baseline. Never bypass ownership/integration
rejections or edit another worktree. If no committed project repo exists, work
directly rather than repeatedly requesting workers. No recursive leaf delegation.
Read-only workers return findings without changing source or shared reports; use
isolated test data, ports, browser sessions and temporary artifact directories.
Checks on the old baseline cannot certify newly integrated changes.

Use focused checks while editing; run the combined build/typecheck/relevant tests
once after integrating a coherent change, and independent final QA when selected.
Repeat broad checks only for new changes, failures or unresolved risk. QA must
reproduce a product defect before proposing a fix; distinguish harness/setup
errors. After two failed attempts with the same hypothesis, inspect new evidence
and revise the hypothesis rather than repeating the same loop. Return a concise
report of changed paths/commits, exact checks/results, evidence and remaining work.
Refresh shared project memory once per meaningful verified milestone.
"""


def install_development_policy(agent, store) -> None:
    from contextlib import contextmanager
    from lyra_lite.settings import _section
    from lyra_lite.workers import WORKERS, Stopped, worker_limit
    from hermes_cli.config import load_config

    # Pin model-facing limits for the lifetime of this conversation's cache.
    limit = worker_limit()
    agent._delegate_max_concurrent_children = limit
    cfg = _section().get("parallel_development") or {}
    local = (load_config().get("terminal") or {}).get("backend", "local") == "local"
    enabled = cfg.get("enabled") is not False and local
    agent._delegate_max_spawn_depth = 2 if enabled else 1
    agent._appling_development_leads = enabled

    def configure(child, *, goal, role):
        child._delegate_max_concurrent_children = limit
        stopped = Stopped(agent, child)

        @contextmanager
        def execution():
            callback = getattr(child, "tool_progress_callback", None)
            def queued():
                if callable(callback):
                    callback("subagent.queued", status="queued", preview="Waiting for a shared worker slot")
            with WORKERS.reserve(1, stopped, wait=True, on_wait=queued) as reservation:
                with reservation.use(stopped) as admitted:
                    yield admitted

        child._delegate_execution_context = execution
        identity = agent_for_goal(goal)
        if enabled and identity in PARALLEL_ROLES and role == "orchestrator":
            child._skip_mcp_refresh = True
            wave = DevelopmentWave(store.root, limit)

            def dispatch(args):
                from tools.delegate_tool import delegate_task
                tasks = args.get("tasks")
                try:
                    tasks = json.loads(tasks) if isinstance(tasks, str) else tasks
                    requested = len(tasks) if isinstance(tasks, list) else 1
                except (ValueError, TypeError):
                    return json.dumps({"error": "Worker tasks must be a JSON list."})
                with WORKERS.reserve(requested, stopped) as reservation:
                    if reservation.count < requested:
                        return json.dumps({"error": f"Only {reservation.count} worker slots available for {requested} tasks; "
                                           "use a smaller independent wave or continue directly. Do not retry in a loop.",
                                           "workers": WORKERS.snapshot()})
                    def configure_leaf(leaf, **_):
                        leaf._delegate_execution_context = lambda: reservation.use(Stopped(agent, child, leaf))

                    child._configure_delegate_child = configure_leaf

                    def execute(prepared, records):
                        store.append_event("worker_plan", agent=identity, workers=requested,
                            reason=str(args.get("context") or
                                       f"{requested} independent {identity} tasks with isolated worktrees; shared limit {limit}")[:400])
                        # Preserve this role's resolved runtime rather than a
                        # global delegation override intended for ordinary CLI use.
                        runtime = {key: getattr(child, key, None) for key in
                                   ("provider", "model", "base_url", "api_key", "api_mode", "request_overrides")}
                        runtime.update(command=getattr(child, "acp_command", None),
                                       args=getattr(child, "acp_args", None),
                                       reasoning=getattr(child, "reasoning_config", None))
                        return delegate_task(tasks=prepared, parent_agent=child, background=False,
                            task_runtimes=[{**runtime, "workspace": r["workspace"]} for r in records])

                    return wave.dispatch(child, args, executor=execute)

            child._dispatch_delegate_task = dispatch

    agent._configure_delegate_child = configure
    # The root AIAgent was built before this host policy was installed. Refresh
    # this one existing schema once, before the conversation's first request.
    from tools.delegate_tool import _build_dynamic_schema_overrides
    for tool in agent.tools:
        function = tool.get("function", {})
        if function.get("name") == "delegate_task":
            function.update(_build_dynamic_schema_overrides(agent))

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


LEAD_CONTEXT = """
You are the development lead. Implement small dependent work directly; parallelize
independent coding work when it helps. Do not impose serial dependencies merely
because tasks appear consecutively in a list. Respect genuine dependencies and
the approved scope. Keep one authoritative schema/interface contract.

For coding helpers use delegate_task(tasks=[...]). Each task's context MUST be a
JSON string: {"owned_paths":["src/feature/","tests/feature/"],"instructions":"..."}.
Paths are project-relative files or directories, without globs. Tasks in a wave
must own disjoint paths. Give each worker the smallest useful contract and tests.
Use only independent tasks with already defined interfaces. Commit/checkpoint
your current work before launching a wave; the primary working tree must be clean.

The host creates a separate Git worktree per worker and integrates only complete,
ownership-valid results via a temporary worktree. Worker paths are returned in
the result if integration is blocked; preserve them and resolve serially. Never
reset, force checkout, overwrite, or bypass a rejected integration. You alone own
shared schemas, dependency manifests/lockfiles, build configuration, Project Brain
and the progress ledger; freeze shared contracts before fan-out. Workers do not
edit the primary project, switch branches, merge, push, or change those shared files.
After integration, run the combined build/typecheck/tests and relevant browser
checks. A successful merge is not proof of functional correctness. Refresh the
Project Brain once with the combined verified result. Report incomplete work
truthfully. No more than the host's bounded worker count in one wave; no nesting
beyond these leaf coding workers. If delegation is unavailable, work serially.
If the project has no committed Git repository, scaffold/checkpoint it first or
continue serially. Never use a repository rooted above the selected project.
"""

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
    def __init__(self, root: Path, max_workers: int = 3):
        self.root = root.resolve()
        self.max_workers = max_workers
        self.lock = threading.Lock()

    def dispatch(self, parent, args: dict, executor=None) -> str:
        if not self.lock.acquire(blocking=False):
            return json.dumps({"error": "A development wave is already running for this lead."})
        wave = None
        try:
            if executor is None:
                from tools.delegate_tool import delegate_task, _get_max_concurrent_children
                limit = min(self.max_workers, _get_max_concurrent_children())
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
                paths = _paths(context.get("owned_paths"))
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
                records.append({"workspace": str(path), "branch": name, "owned_paths": owned[index]})
                prepared.append({"goal": task["goal"], "role": "leaf", "context": (
                    f"Coding workspace: {path}. Use this directory for ALL file and terminal operations. "
                    f"The primary project at {self.root} is read-only to you. "
                    f"Exclusive writable paths: {json.dumps(owned[index])}. "
                    "Do not edit any other paths or shared contracts/config/lockfiles/Project Brain. "
                    "Do not switch branches, merge, push, reset or touch other worktrees. "
                    "Implement and test your assignment, then report exact tests/results and remaining work. "
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
            return json.dumps({**result, "integration": "merged; combined validation is still required",
                               "recovery": str(wave), "workers": records})
        except (ValueError, OSError, subprocess.SubprocessError) as exc:
            return json.dumps({"error": str(exc), "recovery": str(wave) if wave else None,
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


def install_development_policy(agent, store) -> None:
    from lyra_lite.settings import _section

    cfg = _section().get("parallel_development") or {}
    if cfg.get("enabled") is False:
        return
    from hermes_cli.config import load_config

    if (load_config().get("terminal") or {}).get("backend", "local") != "local":
        return  # Host worktrees are meaningful only on the local backend.
    try:
        limit = min(3, max(1, int(cfg.get("max_workers", 3))))
    except (ValueError, TypeError):
        limit = 3
    agent._delegate_max_spawn_depth = 2
    agent._appling_development_leads = True

    def configure(child, *, goal, role):
        if agent_for_goal(goal) == "sw-developer" and role == "orchestrator":
            wave = DevelopmentWave(store.root, limit)
            child._dispatch_delegate_task = lambda args: wave.dispatch(child, args)
            child._skip_mcp_refresh = True

    agent._configure_delegate_child = configure

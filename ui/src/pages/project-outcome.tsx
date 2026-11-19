import type { ProjectDetail, TaskWorker } from "../api";

type Outcome = Pick<ProjectDetail, "phase" | "running" | "paused" | "review_pending" | "inbox" | "queue" | "turn" | "tasks" | "task_workers">;

export function currentBlockedWorkers(project: Outcome | null): TaskWorker[] {
  if (!project || !["build", "qa", "security", "code-review", "accessibility"].includes(project.phase ?? "")) return [];
  const tasks = project.tasks && new Map(project.tasks.map(task => [task.id, task.status]));
  const latest = new Map<string, TaskWorker>();
  for (const worker of project.task_workers ?? []) latest.set(worker.task_id, worker);
  return [...latest.values()].filter(worker =>
    (!tasks || (tasks.has(worker.task_id) && tasks.get(worker.task_id) !== "done")) &&
    ["blocked", "conflict"].includes(worker.status));
}

export function projectIsDelivered(project: Outcome): boolean {
  // Team markers and model prose are presentation, never delivery authority.
  return project.phase === "delivered" && !project.running && !project.paused &&
    !project.review_pending && !project.turn && !project.inbox.length && !project.queue.length &&
    (project.tasks ?? []).every(task => task.status === "done");
}

export function BlockedWork({ workers, running }: { workers: TaskWorker[]; running: boolean }) {
  if (!workers.length) return null;
  return <div className="banner warn" role="status">
    <div>
      <b>Work needs attention — {workers.length} task{workers.length === 1 ? " is" : "s are"} blocked.</b>
      <p className="small">{running ? "Other eligible work continues. " : ""}Finished work and checkpoints are saved.</p>
      {workers.map(worker => <details key={worker.id}>
        <summary>{worker.task_id} · {worker.status === "conflict" ? "Integration needs attention" : "Blocked"}</summary>
        <p className="small">{typeof worker.error === "string" && worker.error ||
          typeof worker.result?.summary === "string" && worker.result.summary || "Inspect the retained worker handoff before continuing."}</p>
        {(Array.isArray(worker.result?.blockers) ? worker.result.blockers : [])
          .filter(blocker => blocker && typeof blocker.kind === "string" && typeof blocker.detail === "string")
          .map((blocker, index) => <p className="small" key={index}>
          {blocker.kind.replaceAll("_", " ")}: {blocker.detail}
          {Array.isArray(blocker.requires_tasks) && blocker.requires_tasks.length ?
            ` · Requires ${blocker.requires_tasks.filter(task => typeof task === "string").join(", ")}` : ""}
        </p>)}
      </details>)}
    </div>
  </div>;
}

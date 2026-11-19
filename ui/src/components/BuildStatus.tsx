import { useEffect, useState } from "react";
import { api } from "../api";
import { currentBlockedWorkers } from "../pages/project-outcome";
import { watchStatus } from "./build-status";

export function BuildStatus({ id }: { id: string }) {
  const [status, setStatus] = useState("Checking project status…");
  useEffect(() => watchStatus(() => api.project(id), project => {
    const blocked = currentBlockedWorkers(project).length;
    const state = project.running ? "Working" : blocked ? `${blocked} tasks blocked` : project.paused ? "Paused" : project.phase === "delivered" ? "Delivered" : project.phase === "implementation_verified" ? "Implementation verified · live acceptance pending" : "Waiting";
    setStatus(`${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · ${state}`);
  }, () => setStatus("Status check unavailable — reconnect to Appling.")), [id]);
  return <div className="small muted" role="status"><p>{status}</p><p>Checks every 5 minutes while this page is open. Activity streams live below.</p></div>;
}

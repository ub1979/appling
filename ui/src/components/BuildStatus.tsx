import { useEffect, useState } from "react";
import { api } from "../api";
import { currentBlockedWorkers } from "../pages/project-outcome";
import { watchStatus } from "./build-status";

export function BuildStatus({ id }: { id: string }) {
  const [status, setStatus] = useState("Checking project status…");
  useEffect(() => watchStatus(() => api.project(id), project => {
    const blocked = currentBlockedWorkers(project).length;
    const state = project.running ? "Working" : blocked ? `${blocked} tasks blocked` : project.paused ? "Paused" : project.phase === "delivered" ? "Delivered" : project.phase === "implementation_verified" ? "Implementation verified · live acceptance pending" : "Waiting";
    const blocks = Object.values((project as { block_status?: Record<string, { status?: string }> }).block_status ?? {});
    const done = blocks.filter(b => b.status === "tested" || b.status === "merged").length;
    const building = blocks.filter(b => b.status === "building").length;
    const deciding = blocks.filter(b => b.status === "blocked").length;
    const blockNote = blocks.length ? ` · blocks: ${done} done${building ? `, ${building} building` : ""}${deciding ? `, ${deciding} need your decision` : ""}` : "";
    setStatus(`${new Date().toLocaleTimeString([], { hour: "2-digit", minute: "2-digit" })} · ${state}${blockNote}`);
  }, () => setStatus("Status check unavailable — reconnect to Appling.")), [id]);
  return <div className="small muted" role="status"><p>{status}</p><p>Checks every 5 minutes while this page is open. Activity streams live below.</p></div>;
}

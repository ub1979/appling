"""Executable protocol peer: real pipes, disk thread state and file changes."""
import json
import os
import sys
from pathlib import Path

state_path = Path(os.environ["FAKE_CODEX_STATE"])
log_path = Path(os.environ["FAKE_CODEX_LOG"])
state = json.loads(state_path.read_text()) if state_path.exists() else {"threads": {}}
thread_id = None
pending = {}
turn_counter = 0


def send(value):
    print(json.dumps(value), flush=True)


def note(method, params):
    send({"method": method, "params": params})


def finish(turn, text="Done", status="completed"):
    note("item/agentMessage/delta", {"threadId": thread_id, "turnId": turn, "delta": text})
    note("item/completed", {"threadId": thread_id, "turnId": turn, "item": {
        "id": "answer", "type": "agentMessage", "phase": "final_answer", "text": text}})
    note("thread/tokenUsage/updated", {"threadId": thread_id, "turnId": turn, "tokenUsage": {"total": {
        "inputTokens": turn_counter * 1000, "cachedInputTokens": turn_counter * 600,
        "outputTokens": turn_counter * 100, "reasoningOutputTokens": turn_counter * 20}}})
    note("turn/completed", {"threadId": thread_id, "turn": {"id": turn, "status": status}})


for line in sys.stdin:
    request = json.loads(line)
    with log_path.open("a") as log:
        log.write(json.dumps({"cwd": os.getcwd(), **request}) + "\n")
    if "method" not in request:
        task = pending.pop(str(request.get("id")), None)
        if task:
            finish(task, "Host response: " + json.dumps(request.get("result")))
        continue
    method, params = request["method"], request.get("params") or {}
    if method == "initialized":
        continue
    if method == "initialize":
        result = {"userAgent": "fake-codex"}
    elif method == "account/read":
        result = {"account": {"type": "apiKey"}, "requiresOpenaiAuth": True}
    elif method == "model/list":
        result = {"data": [{"id": "fake-model", "model": "fake-model"}], "nextCursor": None}
    elif method == "thread/start":
        thread_id = "thread-" + str(len(state["threads"]) + 1)
        state["threads"][thread_id] = {"params": params}
        state_path.write_text(json.dumps(state))
        result = {"thread": {"id": thread_id}}
    elif method == "thread/resume":
        thread_id = params["threadId"]
        result = {"thread": {"id": thread_id}}
    elif method == "turn/start":
        turn_counter += 1
        turn = "turn-" + str(turn_counter)
        send({"id": request["id"], "result": {"turn": {"id": turn, "status": "inProgress"}}})
        text = params["input"][0]["text"]
        if text.startswith("disconnect"):
            sys.exit(0)
        if text.startswith("wait"):
            continue
        if text.startswith(("approval", "resolved")):
            pending["approval-1"] = turn
            send({"id": "approval-1", "method": "item/commandExecution/requestApproval", "params": {
                "threadId": thread_id, "turnId": turn, "itemId": "command", "command": "write outside workspace", "reason": "Test permission"}})
            if text.startswith("resolved"):
                note("serverRequest/resolved", {"threadId": thread_id, "requestId": "approval-1"})
                finish(turn, "Request no longer pending")
        elif text.startswith("unknown"):
            pending["unknown-1"] = turn
            send({"id": "unknown-1", "method": "unsupported/request", "params": {"threadId": thread_id}})
        elif text.startswith("tool "):
            tool = json.loads(text.splitlines()[0][5:])
            pending["tool-1"] = turn
            send({"id": "tool-1", "method": "item/tool/call", "params": {
                "threadId": thread_id, "turnId": turn, "callId": "call-1", **tool}})
        elif text.startswith("write "):
            target = text.splitlines()[0].split(" ", 1)[1]
            Path(target).write_text("written by isolated Codex worker\n")
            note("item/started", {"threadId": thread_id, "turnId": turn, "item": {"id": "edit", "type": "fileChange"}})
            finish(turn, "Wrote " + target)
        else:
            finish(turn, "Hello from native Codex")
        continue
    elif method == "turn/interrupt":
        result = {}
        send({"id": request["id"], "result": result})
        finish(params["turnId"], "", "interrupted")
        continue
    else:
        send({"id": request["id"], "error": {"code": -32601, "message": "Unsupported"}})
        continue
    send({"id": request["id"], "result": result})

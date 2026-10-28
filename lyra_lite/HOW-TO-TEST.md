# Testing Lyra Lite

Lyra Lite is the new, lighter Lyra. Your projects, your linked models and
your builder playbooks are the same as before. What changed is the plumbing
between the screen and the engine.

## 1. Start it

1. If another Lyra is building, stop it first with `./stop.sh` in its own
   folder. Only one Lyra should be building at a time.
2. In a Terminal, go to the Lyra Lite folder and run `./start.sh`.
3. Your browser opens <http://127.0.0.1:9200/> and the Terminal is free
   again. Lyra keeps running (and keeps your Mac awake while it works) even
   if you close the Terminal. Its log is `~/.hermes/logs/appling.log`.

To stop Lyra Lite, run `./stop.sh` in the same folder.

## 2. Test A: build a small app with Hermes (your usual models)

1. Click **Create a new project**, name it `pocket-tasks-hermes`, and leave
   **How much should Lyra build?** on **Personal / one-off**.
2. The button next to **New chat** should say **Hermes ⚙**.
3. Paste this brief:

   > I want a small app called Pocket Tasks: a to-do list for my phone and
   > laptop. I can add a task, tick it done, delete it, and filter All /
   > Active / Done. Tasks stay saved when I close the page. No login, no
   > server. Keep it simple and good-looking.

4. Answer Lyra's questions as you normally would.

## 3. Add a feature to the finished app

Ask for due dates and an overdue filter. Check that the existing tasks remain
saved, the new feature works, and QA checks the changed behavior. Once the
progress ledger marks delivery complete, leave the app idle: it should not
start QA again. A genuinely unfinished later feature should still continue.

## 4. Things worth trying while it builds

| Try this | What should happen |
|---|---|
| Refresh the page, or close and reopen the tab | Nothing is lost: chat, agents, map and questions all come back |
| Close the laptop lid for a while, then open it | Lyra carries on. If a reply was cut off, the chat says so |
| A box appears under **Needs you** | Lyra waits there for your answer, for as long as it takes |
| Press **Stop** | Lyra and its agents stop. The project stays paused until you write again |
| Leave it alone with work remaining | After about 10 quiet minutes Lyra keeps going by itself (switch: **Keep going on its own**) |
| Lyra's rules were changed | A yellow bar offers **Use the new rules** |
| Restart Lyra Lite (`./stop.sh`, then `./start.sh`) during a build | History stays. Agents that were cut off are reported, and Lyra can redo them |

## 5. Inspect the run

Run this in Appling's folder:

```
.venv/bin/python -m lyra_lite.report "~/Appling Projects/pocket-tasks-hermes"
```

The report includes elapsed time, owner messages, watchdog nudges, agents,
approvals, errors and commits. Compare these with the project progress ledger
and the actual app behavior; more review passes alone do not establish a loop.

## 6. If something goes wrong

Tell me:
- the project name;
- roughly what time it happened;
- what you saw.

Everything Lyra did is in that project's `.lyra/events.jsonl` file, so I can
trace it from there.

# Testing Lyra Lite

Lyra Lite is the new, lighter Lyra. Your projects, your linked models and
your builder playbooks are the same as before. What changed is the plumbing
between the screen and the engine.

## 1. Start it

1. If the old Lyra is running, stop it first. In a Terminal, in the Lyra
   folder, run `./stop.sh`. Only one Lyra should be building at a time.
2. In the same folder, run `./lyra.sh`.
3. Your browser opens <http://127.0.0.1:9200/>. Keep the Terminal window
   open; closing it stops Lyra. It also keeps your Mac awake while Lyra works.

To stop Lyra Lite, press **Ctrl+C** in that Terminal window.

## 2. Test A: build a small app with Hermes (your usual models)

1. Click **+ New project**, name it `pocket-tasks-hermes`, and click **Create**.
2. The button next to **New chat** should say **Hermes ⚙**.
3. Paste this brief:

   > I want a small app called Pocket Tasks: a to-do list for my phone and
   > laptop. I can add a task, tick it done, delete it, and filter All /
   > Active / Done. Tasks stay saved when I close the page. No login, no
   > server. Keep it simple and good-looking.

4. Answer Lyra's questions as you normally would.

## 3. Test B: the same app with Claude Code

You need one of the following:
- **An Anthropic API key.** Add `ANTHROPIC_API_KEY=...` to `~/.hermes/.env`,
  then restart Lyra Lite. This is billed per use by Anthropic, not by your
  subscription.
- **Ollama.** In the engine settings, set the model address to
  `http://localhost:11434` and the model to one you have pulled (for example
  `qwen3-coder`). This costs nothing.

Then:
1. Create a project called `pocket-tasks-claude`.
2. Click **Hermes ⚙**, choose **Claude Code**, fill in the model (and the
   address, if you use Ollama), and click **Save**.
3. Paste the same brief, and answer the same way you did in Test A.

## 4. Things worth trying while it builds

| Try this | What should happen |
|---|---|
| Refresh the page, or close and reopen the tab | Nothing is lost: chat, agents, map and questions all come back |
| Close the laptop lid for a while, then open it | Lyra carries on. If a reply was cut off, the chat says so |
| A box appears under **Needs you** | Lyra waits there for your answer, for as long as it takes |
| Press **Stop** | Lyra and its agents stop. The project stays paused until you write again |
| Leave it alone with work remaining | After about 10 quiet minutes Lyra keeps going by itself (switch: **Keep going on its own**) |
| Lyra's rules were changed | A yellow bar offers **Use the new rules** |
| Restart Lyra Lite (Ctrl+C, then `./lyra.sh`) during a build | History stays. Agents that were cut off are reported, and Lyra can redo them |

## 5. Compare the two engines

When both builds are finished (or you stop them), run this in a Terminal, in
the Lyra folder:

```
.venv/bin/python -m lyra_lite.report "~/Lyra Projects/pocket-tasks-hermes" "~/Lyra Projects/pocket-tasks-claude"
```

It prints both projects side by side, with these rows:

| Row | What it counts |
|---|---|
| `wall_hours` | Total time from start to finish |
| `working_hours` | Time Lyra spent actually working |
| `owner_messages` | How many times you had to write |
| `watchdog_nudges` | How many times Lyra had to push itself to continue |
| `agents_started` | How many agents it used |
| `approvals_asked` | How many risky commands it asked about |
| `errors` | Turns that ended in an error |
| `cost_usd` | Cost, for the Claude engine |
| `commits` | How many saved steps are in the project's history |

Open each app as well, and judge which one is actually better.

## 6. If something goes wrong

Tell me:
- the project name;
- roughly what time it happened;
- what you saw.

Everything Lyra did is in that project's `.lyra/events.jsonl` file, so I can
trace it from there.

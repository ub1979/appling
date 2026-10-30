# Appling technical guide

Appling is a file-first project studio built around the Hermes agent runtime. Run `./start.sh` from the repository root and visit <http://127.0.0.1:9200/>. Stop that checkout's server with `./stop.sh`. The older Studio is still available through `./start-studio.sh`, but the Appling launcher starts the `lyra_lite` interface.

The `lyra_lite` package name is historical. Renaming it, or a project's `.lyra/` directory, would break compatibility with saved projects.

## Project state

Each project has a `.lyra/` folder:

- `events.jsonl`: an append-only activity record.
- `messages.jsonl`: the project conversation.
- `inbox/`: questions and approvals waiting for the owner.
- `state.json`: the active queue and project status.
- `memory.db`: project-specific recall.

The project also has a `.sdlc/progress.md` ledger and `.sdlc/project-brain.md` summary for the builders. A browser refresh or a server restart reads the saved project state. A stopped project remains paused until the owner sends a new message. Helpers interrupted by a restart are recorded with an unknown outcome so the owner can inspect them.

Appling uses Hermes for every project. Linked models and effort are selected in **Settings** and apply from the next message. Old Claude Code project state is backed up and migrated when opened; see the migration handling in `store.py` and `settings.py`. Private backups may contain credentials and should stay private.

## Building workflow

In **Create a new project**, choose an app, website, slides, or video, then a project folder. Apps can target web, phone, or desktop. Websites, slides, and videos can start from built-in or owner-added templates. The selected team interviews for requirements, plans work, builds, and records review and QA results. The owner answers questions and approves key steps in the project inbox.

Website projects receive the site checker and a template reference when available. The builder instructions require a successful build and real-browser review before marking website QA complete. A project's actual output and QA evidence still need inspection; the existence of a checker is not proof that a particular build succeeded.

The coordinator delegates implementation to agents. Each agent writes its report back to the project. The optional **Keep going on its own** control can resume unfinished work after an idle period; it does not bypass owner questions or approvals.

## Verification

Use the [hands-on walkthrough](HOW-TO-TEST.md) for a real small project. Local checks:

```bash
scripts/run_tests.sh tests/lyra_lite
cd lyra_lite/ui && npm test && npm run build
```

To summarize a run, use `./.venv/bin/python -m lyra_lite.report /absolute/path/to/project` from the repository root. Compare the report and `.sdlc/progress.md` with the resulting app or site; passing statuses alone do not establish a good result.

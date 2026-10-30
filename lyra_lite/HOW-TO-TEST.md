# Test an Appling build by hand

This walkthrough checks whether a new user can get a useful result from the current Appling interface. It is separate from the automated tests.

## 1. Start Appling and choose a model

From the repository root, run `./start.sh` and open <http://127.0.0.1:9200/> yourself. If this is a fresh installation, connect a model with `./.venv/bin/hermes setup`, then select it in **Settings → Model**. The launcher prints the local log path if startup fails.

## 2. Build a small web app

Select **Create a new project**. Choose **App → Web**, give the project a new folder, and keep the **Personal / one-off** profile. Try this brief:

> Build a small task list that lets me add, finish, and delete tasks. Include All, Active, and Done filters. Save tasks when I close the page. No login or server is needed.

Answer Appling's questions and review approval requests. When the build is reported complete, open the app and check each requested behavior, including persistence after refreshing the page. Record any incorrect or unfinished behavior instead of relying only on the progress label.

## 3. Revise the app

Ask Appling to add due dates and an overdue filter. Check that old tasks remain, the new feature works, and QA covers the changed behavior. A completed project should stay idle; genuinely unfinished work should remain visible in the project map.

## 4. Check continuity

- Refresh or reopen Appling: the project conversation and status should return.
- Press **Stop** in a project: the build should pause until a new owner message.
- Stop and restart the server with `./stop.sh` and `./start.sh`: project files and completed work should remain.
- If a question or approval is waiting, Appling should show it under **Needs you** rather than silently continuing.

## 5. Review the evidence

From the repository root, run:

```bash
./.venv/bin/python -m lyra_lite.report /absolute/path/to/project
```

Compare the report with the project files and `.sdlc/progress.md`. If you file a public issue, include the Appling version, operating system, reproduction steps, and a redacted error. Do not post a project's `.lyra/` state, private files, credentials, or unreviewed logs.

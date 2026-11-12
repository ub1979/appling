# Appling live workflow verification — 12 November 2026

Result: the fresh Pocket Tasks project reached working delivery, independent QA
and final acceptance through Appling's own agents. The operator did not write or
repair any application code in the test project.

## Test and operator actions

- Workspace: `/Users/u/Appling Projects/appling-flow-check`.
- Appling project: `cab8169a37`; Personal browser application.
- Brief: add/edit task titles, completion, confirmed deletion, All/Active/Done,
  remaining count, localStorage persistence, keyboard and responsive behavior.
- Operator used the team, prototype, requirements, implementation-plan and final
  app review controls. No “continue” messages were used to advance the workflow.
- Prototype appeared automatically beside its review controls. Full-page preview
  accepted a new task. The implementation plan was displayed before approval.
- Requirements approval started the planner; plan approval started Development;
  Development's report automatically started independent QA. Each report arrived
  in the conversation; working banners and project phases tracked the agents.
- Browser reload during planning preserved the running agent and conversation.
- Final file state: `running: false`, empty queue, no open inbox requests, final
  reply confirms completed/accepted delivery. Only expected review questions were
  created; no command-permission requests appeared in this test.

## Defects reproduced and fixed during the test

1. The review gate rejected Design's prototype-preparation task because the
   prototype/requirements were not approved yet. Design now joins Requirements
   and Research as preparation work permitted before review. Development still
   waits for approval; a real daemon/delegation regression verifies both paths.
2. Intermediate explanations were in the event log but absent from the durable
   conversation. A requirements card consequently asked for approval without
   showing its draft. Owner messages now persist at turn start, intermediate
   messages persist in the UI transcript, and the UI refreshes them. Cached
   engine history is unchanged. Requirements cards embed the actual draft,
   including when an old card is reopened.

Appling was restarted once to apply these fixes while requirements review was
pending. The prototype approval survived. The pending review reopened with its
full draft; no previously approved review had to be approved again. This was a
live defect-finding run, not a claim that the original unmodified build passed.

## Generated application evidence

- Implementation commit: `2928917003bf2af510fde508c6bf26f28ba9edfd`.
- Independent QA commit: `8d8b01b`.
- Developer checks: 4 model tests and 6 real Chromium browser groups passed.
- QA independently reran both, added 6 independent browser acceptance groups,
  and reported AC1–AC9 PASS. Evidence: `qa/report.md` and `qa/evidence/` in the
  test project. No production app files were changed by QA.
- Operator independently reran the 4 model tests and used the app in the browser:
  add, refresh persistence, edit/save, complete, Done filter, delete dialog and
  cancel preserving the task. The application opened through Appling's Open app
  control and its delivered link, not a manually constructed development setup.
- Delivered preview: `http://127.0.0.1:56412/`; Appling also served its embedded
  App preview. No remote push. The original report1 dashboard was not modified.

## Appling regression validation

```sh
scripts/run_tests.sh tests/lyra_lite/ \
  tests/tools/test_restored_delegation_ownership.py \
  tests/tools/test_open_preview_tool.py \
  tests/skills/test_lyra_independence.py
cd lyra_lite/ui
npm test
npm run build
```

Backend: 302 tests passed, 0 failed across 33 files; no flaky result reported.
UI: 40 tests passed; production build passed. The new regressions execute real persistence and
daemon/restart paths rather than checking source text.

Scope: one small Personal project, Chromium functional QA and browser manual
checks. Safari/Firefox, physical devices and screen-reader speech were not
verified. A completed run is evidence for this workflow, not every future model
response or every possible project.

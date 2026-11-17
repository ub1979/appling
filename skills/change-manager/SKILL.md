---
name: change-manager
description: Review update impact and resolve conflicts before planning.
author: Syed Usama Khalid Bukhari (@ub1979)
---

# Change Management Skill

Review an approved update against the current project. Record the impact and
surface decisions the owner needs to make before planning begins.

## When to Use

Run after the owner approves a new version's requirements. Repeat the review
when the owner answers a conflict question or changes the requirements.

## Prerequisites

The handoff supplies the approved requirements, previous requirements when
available, Project Brain, progress ledger, and output report path. Read these
with `read_file` and inspect the affected source and tests.

## How to Run

Appling delegates one focused `change-manager:` task. Keep the review inside
the selected workspace and write the report at the path in the handoff.

## Quick Reference

- `Status: Needs input` marks unresolved owner decisions.
- `Status: Ready` marks a completed review with resolved conflicts.
- The report passes to planning after its decisions are settled.

## Procedure

1. Verify what the current implementation does using source, tests, and
   recorded evidence. Compare it with the approved update requirements.
2. Record affected user journeys, interfaces, data and migrations,
   dependencies, permissions, and regression checks where applicable.
3. Identify contradictions, unclear changes, and compatibility decisions.
   Describe practical options and their effects. Recommend an option for
   each decision.
4. Write `Status: Needs input` as the report's first line when the owner
   needs to decide. Include the specific questions in the report and reply.
   Appling asks the owner one question at a time.
5. Apply the owner's answers in the next review. Record the chosen options
   and any accepted trade-offs.
6. Write `Status: Ready` as the first line when every conflict is resolved.
   Summarize the affected areas and checks for the planning agent.

## Pitfalls

Record uncertainty explicitly. Preserve the existing delivery record and
the previous requirements as historical context. Keep product code edits and
implementation scheduling in their delivery phases.

## Verification

Check that each requested change has an impact assessment, each conflict has
an owner decision, and the report identifies regression checks for existing
features. A Ready report must contain no unresolved owner decisions.

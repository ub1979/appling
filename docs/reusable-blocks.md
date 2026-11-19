# Reusable application blocks

Status: architecture proposal, not an implemented catalogue.

Appling should retain reusable, versioned application capabilities so another
project can use tested source instead of regenerating the same integration.
Good initial candidates are Telegram transport, CLI subscription-AI connectors,
an engine-independent chat interface, and local task persistence. Keep each
block independent of a particular generated app's workflow/database.

## Packaging

Start with modules/packages that run inside the generated app. Give a block
its own service only when independent deployment, fault isolation, scaling or
language/runtime requirements justify the extra process and operations work.

Each immutable block version should contain:

| Item | Purpose |
|---|---|
| Source, content hash, version and licence/provenance | Reproduce exactly what another project installs |
| Public interface and contracts | State inputs, outputs, errors and supported lifecycle |
| Configuration schema | Identify required settings and secret references without storing secrets |
| Runtime/dependency compatibility | Check whether the block fits the new app's stack |
| Setup, test and shutdown commands | Make validation and cleanup repeatable |
| Raw test evidence and tested revision/environment | State precisely what was verified |
| Known limits, migrations and changelog | Support later upgrades and corrections |

For example, a Telegram transport exposes receive/send/reply operations. The
application supplies credentials, project routing and its approval policy. The
transport does not grant application approvals by itself. A CLI-AI connector
uses that CLI's supported login/session interface; it never exports a user's
OAuth tokens or assumes that a subscription grants access to unrelated APIs.

## Catalogue lifecycle

1. Search the explicitly configured catalogue while planning. Compare the
   interface and verified capabilities with approved requirements.
2. Select a compatible pinned version and show the planned configuration and
   integration work. Do not silently download arbitrary third-party code.
3. Install or vendor that exact version into the project. Keep the upstream
   source hash/version and project-specific changes recorded separately.
4. Run block contract checks and the new app's real integration journeys.
   Missing credentials leave live-provider claims unverified.
5. After useful new code is verified, propose extracting a block with a clean
   interface. Remove app-specific state, private data and credentials; run its
   standalone checks before publishing a new version to the local catalogue.

Keep statuses explicit: candidate, verified for a named environment, deprecated
or blocked. A block's old test evidence can justify reuse, but it cannot mark a
new app delivered. Preserve the app's integration, browser and security checks.

## Changes and parallel execution

Pin each generated project's block versions in a lock manifest. Update a
project intentionally with a migration/diff and affected regression checks;
fixing a catalogue block must not silently modify every installed app.

The planner can schedule independent block adapters and features concurrently
after agreeing contracts. One task owns shared manifests/lockfiles and final
wiring. Host-managed worktrees protect parallel changes; QA checks the combined
app. Reused blocks reduce new work without changing the requirements/design
approval contract.

## Scope of the current patch

The planner now knows to inspect a catalogue when one is explicitly supplied
in its briefing. No catalogue storage, extraction/publishing UI, installation
manager or automatic cross-project reuse is implemented yet. Those form a
separate product feature and should first be proven with one Telegram block
reused in two small apps, including an upgrade and a failed integration check.

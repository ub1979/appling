# Contributing to Appling

Thank you for helping improve Appling. Bug reports, setup feedback, documentation fixes, and focused code changes are welcome.

## Before you start

- Check [Appling issues](https://github.com/ub1979/appling/issues) for an existing report.
- For a code change, describe the behavior you observed and the result you expect. Keep each pull request focused on one problem.
- Read [AGENTS.md](AGENTS.md) for architecture, testing, and release rules. Appling builds on Hermes; keep that distinction clear in changes to the agent runtime.

## Set up a development checkout

You need Python 3.11–3.13, Node.js 20.19+ or 22.12+, [uv](https://docs.astral.sh/uv/), Bash, `lsof`, and `pgrep` for the local launcher.

1. Fork [ub1979/appling](https://github.com/ub1979/appling), then clone your fork:

   ```bash
   git clone https://github.com/YOUR-USERNAME/appling.git
   cd appling
   git remote add upstream https://github.com/ub1979/appling.git
   ```

2. Install the Python and Appling UI dependencies:

   ```bash
   uv sync --extra dev
   cd lyra_lite/ui && npm ci && cd ../..
   ```

3. Run Appling:

   ```bash
   ./start.sh
   ```

   Visit <http://127.0.0.1:9200/>. Run `./.venv/bin/hermes setup` to connect a model if you have not already done so. Stop the local server with `./stop.sh`.

The `lyra_lite/` package and each project's `.lyra/` directory are compatibility paths. Do not rename them as part of a documentation or branding cleanup.

## Make and check a change

Create a branch from an up-to-date `main`, and explain the problem and solution in your commit and pull request. Run the checks that match the files you changed:

```bash
scripts/run_tests.sh tests/lyra_lite
cd lyra_lite/ui && npm test && npm run build
```

For a UI change, also try the affected flow in a browser and include screenshots when they help a reviewer. For changes outside Appling's local UI, use the relevant tests described in [AGENTS.md](AGENTS.md). Documentation-only changes need a link and command review, not a full application test run.

Before pushing a change to this repository, follow the Lyra compatibility version discipline in [AGENTS.md](AGENTS.md): increment the patch component of `LYRA_VERSION` once for the change set and synchronize the changelog, release metadata, desktop package version, and generated version labels. The Appling product version in `lyra_lite/__init__.py` is tracked separately.

Open a pull request against [ub1979/appling](https://github.com/ub1979/appling). Include a short summary, how you verified the change, and any user-visible migration or compatibility effects. Keep credentials, private projects, and raw logs out of commits and public issues.

## Report a problem or suggest a change

Use the [Appling issue forms](https://github.com/ub1979/appling/issues/new/choose). For bugs, include the Appling version shown in the app, your operating system, steps to reproduce, and a redacted error message if available. For a feature request, explain the job you are trying to complete and why the current workflow falls short.

Appling may use Hermes tools and commands internally. If a problem is specifically in upstream Hermes, say so in the report; Appling-specific bugs belong in this repository.

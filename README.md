# Appling

> Describe what you want to make. Work with an AI team to build it in a folder on your own machine.

Appling is a local-first product studio for apps, websites, slide decks, and short videos. It helps you clarify an idea, choose a starting design, build, and review the result. The app and project files run on your computer; you choose the AI model it uses through [Hermes Agent](https://github.com/NousResearch/hermes-agent). A connected cloud model can send prompts to its provider and may incur a subscription or API cost. [Ollama](https://ollama.com/) can run a model locally.

Appling is in beta. Review generated work and test it for your own use before publishing it.

## Quick start

The `start.sh` launcher is for macOS and Linux. It needs Bash, [uv](https://docs.astral.sh/uv/), Node.js 20.19+ or 22.12+, `lsof`, and `pgrep`. The Python project supports Python 3.11 through 3.13; `uv` selects a compatible version. The first start installs Python and UI dependencies and can take several minutes.

```bash
git clone https://github.com/ub1979/appling.git
cd appling
./start.sh
```

Open **<http://127.0.0.1:9200/>** in your browser. The launcher prints the address when Appling is ready; it does not automatically open a browser on a fresh start. Stop it later with `./stop.sh` from the same folder.

Before your first build, connect a model:

```bash
./.venv/bin/hermes setup
```

Follow the provider prompts, then use **Settings → Model** in Appling to choose a linked model. You can use a supported subscription login, an API provider, or a local Ollama model. Provider availability and charges depend on what you connect. Keep API keys in `~/.hermes/.env`; ordinary settings belong in `~/.hermes/config.yaml`.

In Appling, select **Create a new project**, choose a folder and what you are making, pick a template or start from scratch, and describe the result you want. Appling asks questions and brings in building and review agents. It saves each project's work and conversation in that project folder. Use **Open a project** to continue existing work.

For a first try, ask for a small website or web app with a clear outcome. For example: “Build a one-page site for a neighborhood bakery with opening hours, a menu, and a contact link.” Check the result in the browser and ask Appling to revise anything that is wrong.

## What is included

- **Apps:** choose web, phone, or desktop as a target in project setup.
- **Websites:** 19 built-in starting templates with preview designs. The website workflow includes build, browser, and QA checks.
- **Slides and videos:** 6 slide templates and 10 short-video templates.
- **Local project history:** project files, conversations, progress, and approvals are stored with the project; the internal `.lyra/` folder name is retained for compatibility.
- **Model choice:** Appling uses Hermes to connect to supported models. Your model choice and provider determine where inference runs and what it costs.

Templates are starting designs, not finished customer projects. The output still needs your review before it is shared or deployed.

## Development and support

See [Contributing](CONTRIBUTING.md) for a development setup and pull request guide. For an Appling bug or setup problem, use the [Appling issue tracker](https://github.com/ub1979/appling/issues/new/choose). Include steps to reproduce and a redacted error message; do not publish API keys, private project files, or raw diagnostic archives.

The [architecture overview](APPLING.md) and [technical guide](lyra_lite/README.md) explain the current workflow, with a [hands-on test walkthrough](lyra_lite/HOW-TO-TEST.md).

## History and credits

Appling grew out of a project previously called Lyra. Some internal paths, Python packages, and older changelog entries retain that name so existing installations and projects continue to work. The user-facing product and this repository are **Appling**.

Appling builds on [Hermes Agent](https://github.com/NousResearch/hermes-agent) by Nous Research. Hermes provides the agent runtime and model connections; Appling adds the project studio and guided building workflow. See the repository [license](LICENSE).

# Appling architecture

Appling is the product studio in `lyra_lite/`. The package name comes from its earlier name, Lyra, and remains stable for saved-project compatibility. The main entry point is `./start.sh`, which starts the local interface at <http://127.0.0.1:9200/>. The separate, older Studio uses `./start-studio.sh`.

The UI in `lyra_lite/ui/` sends requests to the local server in `lyra_lite/server.py`. Project state is stored with the owner's project files in `.lyra/`; `lyra_lite/store.py` handles persistence and migration. The runner and coordinator in `lyra_lite/` orchestrate the work, while Hermes supplies model connections and the agent runtime. The Ultimate Builder skills supply building and checking workflows.

The owner chooses a project type, folder, and optional starting template. Appling collects requirements, plans tasks, delegates building, and records QA and approval state. Project data survives a browser refresh and server restart. A model connected through Hermes may run locally or through a remote provider.

For installation and a first project, read [README.md](README.md). For implementation details and verification, read [the technical guide](lyra_lite/README.md) and [test walkthrough](lyra_lite/HOW-TO-TEST.md).

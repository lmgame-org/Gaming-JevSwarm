# jev-swarm

Collective-behaviour studies where **every agent picks its next action with Jev** from its own local information.
Each study is a separate sub-project with its own launch screen, live viewer, tests and run logs.

| Sub-project | What it studies | Launch (from the repo root) | Viewer |
|---|---|---|---|
| [`fish/`](fish/README.md) | Fish schooling under predator attack: local vision, escape waves, fragmentation | `python3 run.py fish` | http://127.0.0.1:8777 |

```
run.py              launcher: python3 run.py <fish|honeybee|list> [--port N]
common/swarmcore/   shared code: Jev and chat model clients, key lookup, web-server helpers
fish/               fish schooling simulator (package jevswarm, web/, tests/, docs/, runs/)
```

Setup is one dependency: `python3 -m pip install numpy`. Models and keys are the same for every sub-project:
Jev `typesafe/jev-1.13` through OpenRouter (key file `~/.credentials/openrouter_api_key`) for agent decisions,
and OpenAI `gpt-6-astra` (key file `~/.credentials/llm_api_key`) for the analyst. Keys are read at call time and
are never logged, written to run logs or sent to the browser.

Each sub-project also runs on its own, for example `cd fish && python3 -m jevswarm`.

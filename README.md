# jev-swarm

Collective-behaviour studies where **every agent picks its next action with Jev** from its own local information.
Each study is a separate sub-project with its own launch screen, live viewer, tests and run logs.

| Sub-project | What it studies | Launch (from the repo root) | Viewer |
|---|---|---|---|
| [`fish/`](fish/README.md) | Fish schooling under predator attack: local vision, escape waves, fragmentation | `python3 run.py fish` | http://127.0.0.1:8777 |
| [`honeybee/`](honeybee/README.md) | Honeybee nest-site selection: waggle dances, quorum, misinformation, stubborn and biased scouts | `python3 run.py honeybee` | http://127.0.0.1:8779 |
| [`holmes/`](holmes/README.md) | The Irregulars: a seeded Sherlock Holmes case solved by one detective (Jev vs gpt-6-astra vs rule) or by a swarm of 100 Jev Irregulars with lies, limited range and quorum voting | `python3 run.py holmes` | http://127.0.0.1:8781 |

```
run.py              launcher: python3 run.py <fish|honeybee|holmes|list> [--port N]
common/swarmcore/   shared code: Jev and chat model clients, key lookup, web-server helpers
fish/               fish schooling simulator (package jevswarm, web/, tests/, docs/, runs/)
honeybee/           honeybee nest-site selection simulator (package beeswarm, web/, tests/, docs/, runs/)
holmes/             The Irregulars detective game: case engine, Solo and Swarm modes (package irregulars)
```

Setup is one dependency: `python3 -m pip install numpy`. Models and keys are the same for every sub-project:
Jev `typesafe/jev-1.13` through OpenRouter (key file `~/.credentials/openrouter_api_key`) for agent decisions,
and OpenAI `gpt-6-astra` (key file `~/.credentials/llm_api_key`) for the analyst and holmes's "genius" detective. Keys are read at call time and
are never logged, written to run logs or sent to the browser.

Each sub-project also runs on its own, for example `cd fish && python3 -m jevswarm` or
`cd honeybee && python3 -m beeswarm`. To add another study, create a folder with its own package, `web/` and
`tests/`, import shared code from `swarmcore`, and register it in `run.py`.

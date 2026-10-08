"""Where API keys come from. Keys are read only at call time (see read_key) and never logged or sent to the browser.

A key source is a string, either a file path or `env:NAME` for an environment variable. Configs and the launch screen
only ever hold the source, never the key itself. Lookup order for the defaults: the first existing key file below,
then the environment variable, then the first file path (so the launch screen shows where it expects the key).
"""
import os

JEV_KEY_CANDIDATES = [
    "/workspace/.credentials/openrouter_api_key",
    "~/.credentials/openrouter_api_key",
]
CHAT_KEY_CANDIDATES = [
    "/workspace/.credentials/llm_api_key",
    "~/.credentials/llm_api_key",
    "~/.credentials/astra_api_key",
    "~/.credentials/openai_key",
]
JEV_KEY_ENV = "OPENROUTER_API_KEY"
CHAT_KEY_ENV = "OPENAI_API_KEY"
ENV_FOR = {id(JEV_KEY_CANDIDATES): JEV_KEY_ENV, id(CHAT_KEY_CANDIDATES): CHAT_KEY_ENV}


def first_key(paths, env=None):
    """The default key source for a role: an existing file, else `env:NAME` when that variable is set."""
    for p in paths:
        if os.path.isfile(os.path.expanduser(p)):
            return p
    env = env or ENV_FOR.get(id(paths))
    if env and os.environ.get(env):
        return f"env:{env}"
    return paths[0]


def read_key(source):
    """The key for a source (file path or env:NAME), or None. Callers must never log or return the value."""
    source = (source or "").strip()
    if source.startswith("env:"):
        return (os.environ.get(source[4:]) or "").strip() or None
    path = os.path.expanduser(source)
    if not path or not os.path.isfile(path):
        return None
    with open(path) as f:
        key = f.read().strip()
    return key or None


def key_files():
    """Which candidate key sources exist (names only, never contents)."""
    out = [{"path": p, "exists": os.path.isfile(os.path.expanduser(p))} for p in JEV_KEY_CANDIDATES + CHAT_KEY_CANDIDATES]
    out += [{"path": f"env:{e}", "exists": bool(os.environ.get(e))} for e in (JEV_KEY_ENV, CHAT_KEY_ENV)]
    return out

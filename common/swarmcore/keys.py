"""Where to look for API key files. Keys are read only at call time (see llm.read_key) and never logged."""
import os

# First readable file wins.
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


def first_key(paths):
    for p in paths:
        if os.path.isfile(os.path.expanduser(p)):
            return p
    return paths[0]


def key_files():
    """Which candidate key files exist (paths only, never contents)."""
    return [{"path": p, "exists": os.path.isfile(os.path.expanduser(p))}
            for p in JEV_KEY_CANDIDATES + CHAT_KEY_CANDIDATES]

"""Minimal OpenAI-compatible chat client (OpenAI or OpenRouter), stdlib only.

API keys are read at call time from a key source (a file path or env:NAME, see keys.py). The key value is never logged,
returned, or included in error messages.
"""
import json
import re
import time
import urllib.error
import urllib.request

from .keys import read_key  # noqa: F401  (re-exported: llm.read_key)

PROVIDERS = {
    "openai": "https://api.openai.com/v1",
    "openrouter": "https://openrouter.ai/api/v1",
    "typesafe": "https://api.typesafe.ai/v1",
}

# Default model per role and provider.
DEFAULT_MODELS = {
    "narrator": {"openai": "gpt-6-astra", "openrouter": "openai/gpt-6-astra"},
    "jev": {"openrouter": "typesafe/jev-1.13", "typesafe": "jev-1.13", "openai": "gpt-6-astra"},
}


def is_jev_model(model):
    """Jev (TypeSafe System One) models answer typed questions, not chat."""
    return "jev" in (model or "").split("/")[-1].lower()


def detect_provider(path):
    """Guess the provider from a key file's prefix. Returns None if unreadable."""
    key = read_key(path)
    if not key:
        return None
    return "openrouter" if key.startswith("sk-or-") else "openai"


class LLMError(Exception):
    pass


class LLMClient:
    def __init__(self, provider="auto", model=None, key_path=None, timeout=60,
                 temperature=0.7, role="narrator"):
        self.key_path = key_path
        if provider == "auto":
            provider = detect_provider(key_path) or "openai"
        self.provider = provider
        self.base_url = PROVIDERS[provider]
        self.model = model or DEFAULT_MODELS[role].get(provider) or DEFAULT_MODELS["narrator"]["openai"]
        self.timeout = timeout
        self.temperature = temperature
        self.last_usage = {}

    def chat(self, system, user, json_mode=True, max_tokens=1200, retries=2):
        key = read_key(self.key_path)
        if not key:
            raise LLMError(f"no API key readable at {self.key_path!r}")
        body = {
            "model": self.model,
            "messages": [{"role": "system", "content": system},
                         {"role": "user", "content": user}],
            "temperature": self.temperature,
            "max_completion_tokens" if self.provider == "openai" else "max_tokens": max_tokens,
        }
        if json_mode:
            body["response_format"] = {"type": "json_object"}
        headers = {"Content-Type": "application/json",
                   "Authorization": f"Bearer {key}"}
        if self.provider == "openrouter":
            headers["X-Title"] = "jev-swarm-games"
        last = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(
                self.base_url + "/chat/completions",
                data=json.dumps(body).encode(), headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read())
                self.last_usage = data.get("usage") or {}
                content = data["choices"][0]["message"]["content"] or ""
                return parse_json(content) if json_mode else content
            except urllib.error.HTTPError as e:
                detail = e.read()[:300].decode(errors="replace")
                last = LLMError(f"HTTP {e.code} from {self.provider}: {detail}")
                if e.code in (400, 401, 403, 404):
                    # Newer models reject some sampling params; drop the one named and retry.
                    if e.code == 400:
                        dropped = False
                        for param in ("temperature", "response_format", "max_tokens", "max_completion_tokens"):
                            if param in detail and param in body:
                                val = body.pop(param)
                                if param == "max_tokens":
                                    body["max_completion_tokens"] = val
                                dropped = True
                                break
                        if dropped:
                            continue
                    break
            except (urllib.error.URLError, TimeoutError, KeyError, ValueError) as e:
                last = LLMError(f"{type(e).__name__}: {e}")
            time.sleep(1.5 * (attempt + 1))
        raise last or LLMError("unknown LLM failure")


def parse_json(text):
    text = text.strip()
    try:
        return json.loads(text)
    except ValueError:
        pass
    m = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.S)
    if m:
        return json.loads(m.group(1))
    start, end = text.find("{"), text.rfind("}")
    if start >= 0 and end > start:
        return json.loads(text[start:end + 1])
    raise ValueError("no JSON object in model output")


class JevClient:
    """Client for Jev, TypeSafe's System One decision model.

    Jev takes a `state` plus a map of typed questions (noul = yes/no probability,
    choice, score) and returns typed answers. It is served by TypeSafe directly
    and by OpenRouter's System One endpoint.
    """

    def __init__(self, provider="openrouter", model=None, key_path=None, timeout=30):
        if provider == "auto":
            provider = detect_provider(key_path) or "openrouter"
        if provider not in ("openrouter", "typesafe"):
            provider = "openrouter"
        self.provider = provider
        self.key_path = key_path
        self.model = model or DEFAULT_MODELS["jev"][provider]
        if provider == "typesafe":
            self.model = self.model.split("/")[-1]
        self.url = PROVIDERS[provider] + "/systemone"
        self.timeout = timeout

    def ask(self, state, questions, retries=2):
        key = read_key(self.key_path)
        if not key:
            raise LLMError(f"no API key readable at {self.key_path!r}")
        body = json.dumps({"model": self.model, "state": state, "questions": questions}).encode()
        headers = {"Content-Type": "application/json", "Authorization": f"Bearer {key}", "X-Title": "jev-swarm-games"}
        last = None
        for attempt in range(retries + 1):
            req = urllib.request.Request(self.url, data=body, headers=headers, method="POST")
            try:
                with urllib.request.urlopen(req, timeout=self.timeout) as r:
                    data = json.loads(r.read())
                return data.get("answers") or {}, {"usage": data.get("usage") or {},
                                                   "model": data.get("model") or self.model}
            except urllib.error.HTTPError as e:
                detail = e.read()[:300].decode(errors="replace")
                last = LLMError(f"HTTP {e.code} from {self.provider} System One: {detail}")
                if e.code in (400, 401, 403, 404, 422):
                    break
                if e.code == 429:
                    time.sleep(float(e.headers.get("retry-after") or 2))
            except (urllib.error.URLError, TimeoutError, ValueError) as e:
                last = LLMError(f"{type(e).__name__}: {e}")
            time.sleep(1.0 * (attempt + 1))
        raise last or LLMError("unknown Jev failure")

"""Configurable chat-model backend. Local Ollama is the default (zero cost, no API key needed to
run anything in this repo) — Claude is opt-in via config.yaml or env, for anyone who wants to
compare a frontier model's reasoning quality on the same ambiguity-analysis / code-review nodes.
"""

from __future__ import annotations

import os

from config import Config


def get_chat_model(config: Config):
    if config.model_provider == "anthropic":
        from langchain_anthropic import ChatAnthropic

        if not os.environ.get("ANTHROPIC_API_KEY"):
            raise RuntimeError(
                "model_provider=anthropic requires ANTHROPIC_API_KEY. Set model_provider=ollama "
                "in config.yaml (or unset MODEL_PROVIDER) to use the local model instead."
            )
        return ChatAnthropic(model=config.resolved_model_name, temperature=0, max_tokens=2048)

    if config.model_provider == "ollama":
        from langchain_ollama import ChatOllama

        return ChatOllama(model=config.resolved_model_name, temperature=0)

    raise ValueError(f"unknown model_provider '{config.model_provider}', expected 'ollama' or 'anthropic'")

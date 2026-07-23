"""Loads configuration (Riot API key etc.) from environment / .env file."""
from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv


@dataclass(frozen=True)
class Config:
    riot_api_key: str
    anthropic_api_key: str | None


def load_config() -> Config:
    load_dotenv()
    api_key = os.environ.get("RIOT_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError(
            "RIOT_API_KEY ist nicht gesetzt. Kopiere .env.example zu .env und trage "
            "deinen Riot Developer API Key ein (https://developer.riotgames.com/)."
        )
    anthropic_api_key = os.environ.get("ANTHROPIC_API_KEY", "").strip() or None
    return Config(riot_api_key=api_key, anthropic_api_key=anthropic_api_key)

"""Duenner HTTP-Wrapper um die Riot-API-Endpunkte, die wir brauchen.

Deckt bewusst nur Account-V1 und Match-V5 ab (strukturierte Match-/Timeline-Daten).
Kein Coverage fuer League-V4, Spectator-V4 etc. - die brauchen wir fuer Post-Game-
Analyse eines einzelnen Matches nicht.
"""
from __future__ import annotations

import time
from collections import deque

import requests

# Match-V5 / Account-V1 nutzen "continental" Routing, nicht die Platform-Region.
# Deckt die gaengigsten Platform-Regionen ab; fehlende Regionen (z.B. neuere SEA-
# Platforms) muessten hier ergaenzt werden.
PLATFORM_TO_CONTINENT = {
    "na1": "americas",
    "br1": "americas",
    "la1": "americas",
    "la2": "americas",
    "oc1": "americas",
    "euw1": "europe",
    "eun1": "europe",
    "tr1": "europe",
    "ru": "europe",
    "kr": "asia",
    "jp1": "asia",
}


class RiotApiError(RuntimeError):
    pass


class RateLimiter:
    """Einfacher Sliding-Window-Limiter fuer mehrere gleichzeitige Limits."""

    def __init__(self, limits: list[tuple[int, float]]):
        self._limits = limits
        self._calls: list[deque[float]] = [deque() for _ in limits]

    def acquire(self) -> None:
        while True:
            now = time.monotonic()
            wait_for = 0.0
            for (max_calls, window_s), calls in zip(self._limits, self._calls):
                while calls and now - calls[0] > window_s:
                    calls.popleft()
                if len(calls) >= max_calls:
                    wait_for = max(wait_for, window_s - (now - calls[0]) + 0.05)
            if wait_for <= 0:
                break
            time.sleep(wait_for)
        now = time.monotonic()
        for calls in self._calls:
            calls.append(now)


class RiotClient:
    def __init__(self, api_key: str, platform: str, timeout_s: float = 10.0):
        if platform not in PLATFORM_TO_CONTINENT:
            raise RiotApiError(
                f"Unbekannte Platform-Region '{platform}'. Bekannt: "
                f"{sorted(PLATFORM_TO_CONTINENT)}"
            )
        self._api_key = api_key
        self._platform = platform
        self._continent = PLATFORM_TO_CONTINENT[platform]
        self._timeout_s = timeout_s
        # Personal Dev Key Limits: 20 req/1s, 100 req/2min.
        self._limiter = RateLimiter([(20, 1.0), (100, 120.0)])

    def _get(self, base: str, path: str) -> dict:
        url = f"https://{base}.api.riotgames.com{path}"
        headers = {"X-Riot-Token": self._api_key}
        for attempt in range(5):
            self._limiter.acquire()
            resp = requests.get(url, headers=headers, timeout=self._timeout_s)
            if resp.status_code == 429:
                retry_after = float(resp.headers.get("Retry-After", "1"))
                time.sleep(retry_after + 0.1)
                continue
            if resp.status_code >= 500:
                time.sleep(1.0 + attempt)
                continue
            if resp.status_code == 404:
                raise RiotApiError(f"Nicht gefunden (404): {path}")
            if resp.status_code == 403:
                raise RiotApiError(
                    "Riot API meldet 403 Forbidden - API Key ungueltig oder abgelaufen "
                    "(Personal Dev Keys gelten nur 24h)."
                )
            if not resp.ok:
                raise RiotApiError(f"Riot API Fehler {resp.status_code} bei {path}: {resp.text}")
            return resp.json()
        raise RiotApiError(f"Riot API: zu viele Retries bei {path}")

    def get_puuid_by_riot_id(self, game_name: str, tag_line: str) -> str:
        data = self._get(
            self._continent, f"/riot/account/v1/accounts/by-riot-id/{game_name}/{tag_line}"
        )
        return data["puuid"]

    def get_match_ids(self, puuid: str, count: int = 5) -> list[str]:
        data = self._get(
            self._continent,
            f"/lol/match/v5/matches/by-puuid/{puuid}/ids?start=0&count={count}",
        )
        return data

    def get_match(self, match_id: str) -> dict:
        return self._get(self._continent, f"/lol/match/v5/matches/{match_id}")

    def get_timeline(self, match_id: str) -> dict:
        return self._get(self._continent, f"/lol/match/v5/matches/{match_id}/timeline")

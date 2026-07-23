"""Data-Dragon-Client: patch-genaue Champion-Ability-Cooldowns fuer die
Ability-Usage-Analyse. Reiner I/O-Layer (analog zu fetch.py). Netzwerk-/
Parsing-Fehler werden hier als DDragonError nach oben gereicht - der Aufrufer
(cli.py) faengt sie ab und laesst den Rest des Reports unbeeintraechtigt
weiterlaufen, statt abzustuerzen.
"""
from __future__ import annotations

import json
from pathlib import Path

import requests

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent.parent / "cache" / "ddragon"


class DDragonError(RuntimeError):
    pass


def _cache_get_or_fetch(cache_dir: Path, filename: str, url: str) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = cache_dir / filename
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    resp = requests.get(url, timeout=10)
    if not resp.ok:
        raise DDragonError(f"Data Dragon Fehler {resp.status_code} bei {url}")
    data = resp.json()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def resolve_version(game_version: str, cache_dir: Path = DEFAULT_CACHE_DIR) -> str:
    """Bildet Riots 'gameVersion' (z.B. '16.2.740.1491') auf eine existierende
    Data-Dragon-Version ab (z.B. '16.2.1'). Data Dragon fuehrt nur major.minor.patch,
    Riots interne Build-Nummern (3./4. Segment) werden ignoriert.
    """
    parts = game_version.split(".")
    if len(parts) < 2:
        raise DDragonError(f"Unerwartetes gameVersion-Format: {game_version!r}")
    major_minor = f"{parts[0]}.{parts[1]}"
    versions = _cache_get_or_fetch(
        cache_dir, "versions.json", "https://ddragon.leagueoflegends.com/api/versions.json"
    )
    candidates = [v for v in versions if v.startswith(major_minor + ".")]
    if not candidates:
        raise DDragonError(f"Keine Data-Dragon-Version fuer Patch {major_minor} gefunden")
    return candidates[0]


def get_ability_cooldowns(
    champion_name: str, version: str, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[list[float]]:
    """Gibt cooldowns[slot][rank_index] zurueck, slot 0-3 = Q/W/E/R.

    Verifiziert gegen echte Riot-/Data-Dragon-Daten: die Reihenfolge der
    'spells'-Liste und die spellSlot-Werte in den Timeline-Combat-Log-Events
    stimmen ueberein (slot 0=Q, 1=W, 2=E, 3=R).
    """
    url = (
        f"https://ddragon.leagueoflegends.com/cdn/{version}/data/en_US/champion/"
        f"{champion_name}.json"
    )
    data = _cache_get_or_fetch(cache_dir, f"champion_{version}_{champion_name}.json", url)
    try:
        champ_data = data["data"][champion_name]
    except KeyError as exc:
        raise DDragonError(
            f"Champion '{champion_name}' nicht in Data-Dragon-Antwort gefunden"
        ) from exc
    return [spell["cooldown"] for spell in champ_data["spells"]]

"""Orchestriert Riot-ID -> PUUID -> Matchliste -> Match+Timeline und cached
die rohen JSON-Antworten auf Platte, um waehrend der Entwicklung nicht staendig
gegen die (rate-limitierte) Live-API zu laufen.
"""
from __future__ import annotations

import json
from pathlib import Path

from .models import (
    Frame,
    MatchContext,
    MatchSummary,
    Participant,
    ParticipantFrame,
    Position,
    TimelineEvent,
)
from .riot_client import RiotClient

DEFAULT_CACHE_DIR = Path(__file__).resolve().parent.parent.parent / "cache"


def _cache_path(cache_dir: Path, match_id: str, suffix: str) -> Path:
    return cache_dir / f"{match_id}{suffix}.json"


def _load_or_fetch(cache_dir: Path, match_id: str, suffix: str, fetch_fn) -> dict:
    cache_dir.mkdir(parents=True, exist_ok=True)
    path = _cache_path(cache_dir, match_id, suffix)
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    data = fetch_fn()
    path.write_text(json.dumps(data), encoding="utf-8")
    return data


def resolve_puuid(client: RiotClient, riot_id: str) -> str:
    if "#" not in riot_id:
        raise ValueError("Riot-ID muss im Format 'Name#Tag' angegeben werden")
    game_name, tag_line = riot_id.split("#", 1)
    return client.get_puuid_by_riot_id(game_name, tag_line)


def pick_match_id(client: RiotClient, puuid: str, match_selector: str) -> str:
    if match_selector != "latest":
        return match_selector
    match_ids = client.get_match_ids(puuid, count=1)
    if not match_ids:
        raise RuntimeError("Keine Matches fuer diesen Account gefunden")
    return match_ids[0]


def parse_match_summary(match_json: dict, puuid: str) -> MatchSummary:
    info = match_json["info"]
    p = next((p for p in info["participants"] if p["puuid"] == puuid), None)
    if p is None:
        raise KeyError("Kein Teilnehmer mit dieser PUUID in diesem Match gefunden")
    return MatchSummary(
        match_id=match_json["metadata"]["matchId"],
        game_creation_ms=info.get("gameCreation", 0),
        game_duration_s=info["gameDuration"],
        champion_name=p["championName"],
        team_position=p.get("teamPosition", ""),
        win=p["win"],
        kills=p["kills"],
        deaths=p["deaths"],
        assists=p["assists"],
    )


def get_recent_match_summaries(
    client: RiotClient, puuid: str, count: int = 10, cache_dir: Path = DEFAULT_CACHE_DIR
) -> list[MatchSummary]:
    """Liste der letzten `count` Matches ohne Timeline-Fetch (siehe MatchSummary-
    Docstring). Nutzt denselben Match-JSON-Cache wie fetch_match_context - ein
    Match, das schon einzeln analysiert wurde, wird hier nicht erneut gefetcht."""
    match_ids = client.get_match_ids(puuid, count=count)
    summaries = []
    for match_id in match_ids:
        match_json = _load_or_fetch(
            cache_dir, match_id, "", lambda mid=match_id: client.get_match(mid)
        )
        summaries.append(parse_match_summary(match_json, puuid))
    return summaries


def fetch_match_context(
    client: RiotClient, match_id: str, cache_dir: Path = DEFAULT_CACHE_DIR
) -> MatchContext:
    match_json = _load_or_fetch(cache_dir, match_id, "", lambda: client.get_match(match_id))
    timeline_json = _load_or_fetch(
        cache_dir, match_id, "_timeline", lambda: client.get_timeline(match_id)
    )
    return parse_match_context(match_json, timeline_json)


def parse_match_context(match_json: dict, timeline_json: dict) -> MatchContext:
    info = match_json["info"]
    participants = tuple(
        Participant(
            participant_id=p["participantId"],
            puuid=p["puuid"],
            team_id=p["teamId"],
            champion_name=p["championName"],
            team_position=p.get("teamPosition", ""),
            win=p["win"],
            kills=p["kills"],
            deaths=p["deaths"],
            assists=p["assists"],
            total_cs=p.get("totalMinionsKilled", 0) + p.get("neutralMinionsKilled", 0),
            vision_score=p.get("visionScore", 0),
            wards_placed=p.get("wardsPlaced", 0),
            wards_killed=p.get("wardsKilled", 0),
            gold_earned=p.get("goldEarned", 0),
        )
        for p in info["participants"]
    )

    tl_info = timeline_json["info"]
    frames = []
    for raw_frame in tl_info["frames"]:
        participant_frames: dict[int, ParticipantFrame] = {}
        for pid_str, pf in raw_frame.get("participantFrames", {}).items():
            pos = pf.get("position") or {"x": 0, "y": 0}
            champion_stats = pf.get("championStats", {})
            participant_frames[int(pid_str)] = ParticipantFrame(
                participant_id=int(pid_str),
                position=Position(x=pos["x"], y=pos["y"]),
                current_gold=pf.get("currentGold", 0),
                total_gold=pf.get("totalGold", 0),
                level=pf.get("level", 1),
                xp=pf.get("xp", 0),
                minions_killed=pf.get("minionsKilled", 0),
                jungle_minions_killed=pf.get("jungleMinionsKilled", 0),
                health=champion_stats.get("health", 0),
                health_max=champion_stats.get("healthMax", 0),
                ability_haste=champion_stats.get("abilityHaste", 0),
            )
        events = []
        for ev in raw_frame.get("events", []):
            pos = ev.get("position")
            events.append(
                TimelineEvent(
                    type=ev["type"],
                    timestamp_ms=ev["timestamp"],
                    killer_id=ev.get("killerId"),
                    victim_id=ev.get("victimId"),
                    creator_id=ev.get("creatorId"),
                    assisting_participant_ids=tuple(ev.get("assistingParticipantIds", [])),
                    position=Position(x=pos["x"], y=pos["y"]) if pos else None,
                    ward_type=ev.get("wardType"),
                    raw=ev,
                )
            )
        frames.append(
            Frame(
                timestamp_ms=raw_frame["timestamp"],
                participant_frames=participant_frames,
                events=tuple(events),
            )
        )

    return MatchContext(
        match_id=match_json["metadata"]["matchId"],
        game_duration_s=info["gameDuration"],
        frame_interval_ms=tl_info.get("frameInterval", 60000),
        participants=participants,
        frames=tuple(frames),
        game_version=info.get("gameVersion", ""),
        game_creation_ms=info.get("gameCreation", 0),
    )

"""Interne Datenmodelle, entkoppelt vom rohen Riot-API-JSON."""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Position:
    x: int
    y: int

    def distance_to(self, other: "Position") -> float:
        return ((self.x - other.x) ** 2 + (self.y - other.y) ** 2) ** 0.5


@dataclass(frozen=True)
class Participant:
    participant_id: int
    puuid: str
    team_id: int
    champion_name: str
    team_position: str  # TOP, JUNGLE, MIDDLE, BOTTOM, UTILITY (kann bei Sonderfaellen leer sein)
    win: bool
    kills: int
    deaths: int
    assists: int
    total_cs: int
    vision_score: int
    wards_placed: int
    wards_killed: int
    gold_earned: int


@dataclass(frozen=True)
class ParticipantFrame:
    participant_id: int
    position: Position
    current_gold: int
    total_gold: int
    level: int
    xp: int
    minions_killed: int
    jungle_minions_killed: int
    health: int = 0
    health_max: int = 0
    ability_haste: int = 0

    @property
    def total_cs(self) -> int:
        return self.minions_killed + self.jungle_minions_killed

    @property
    def health_ratio(self) -> float | None:
        """None wenn unbekannt. health==0 bedeutet oft 'Frame nach dem Tod erfasst',
        nicht zwingend 'lebend bei 0 HP' - Aufrufer muessen das beruecksichtigen."""
        if self.health_max <= 0:
            return None
        return self.health / self.health_max


@dataclass(frozen=True)
class TimelineEvent:
    type: str
    timestamp_ms: int
    killer_id: int | None = None
    victim_id: int | None = None
    creator_id: int | None = None
    assisting_participant_ids: tuple[int, ...] = field(default_factory=tuple)
    position: Position | None = None
    ward_type: str | None = None
    raw: dict = field(default_factory=dict)

    @property
    def timestamp_s(self) -> int:
        return self.timestamp_ms // 1000


@dataclass(frozen=True)
class Frame:
    timestamp_ms: int
    participant_frames: dict[int, ParticipantFrame]
    events: tuple[TimelineEvent, ...]


@dataclass(frozen=True)
class MatchContext:
    match_id: str
    game_duration_s: int
    frame_interval_ms: int
    participants: tuple[Participant, ...]
    frames: tuple[Frame, ...]
    game_version: str = ""

    def participant_by_id(self, participant_id: int) -> Participant:
        for p in self.participants:
            if p.participant_id == participant_id:
                return p
        raise KeyError(f"Kein Teilnehmer mit participant_id={participant_id}")

    def participant_by_puuid(self, puuid: str) -> Participant:
        for p in self.participants:
            if p.puuid == puuid:
                return p
        raise KeyError("Kein Teilnehmer mit dieser PUUID in diesem Match gefunden")

    def lane_opponent(self, participant_id: int) -> Participant | None:
        me = self.participant_by_id(participant_id)
        if not me.team_position:
            return None
        for p in self.participants:
            if p.team_id != me.team_id and p.team_position == me.team_position:
                return p
        return None

    def frame_at_or_before(self, timestamp_ms: int) -> Frame | None:
        candidates = [f for f in self.frames if f.timestamp_ms <= timestamp_ms]
        return max(candidates, key=lambda f: f.timestamp_ms) if candidates else None

    def frame_nearest(self, timestamp_ms: int) -> Frame | None:
        if not self.frames:
            return None
        return min(self.frames, key=lambda f: abs(f.timestamp_ms - timestamp_ms))


@dataclass(frozen=True)
class Finding:
    category: str  # "laning" | "vision" | "deaths"
    valence: str  # "positive" | "negative"
    impact: int  # 1 (klein) .. 5 (gross)
    timestamp_s: int
    title: str
    description: str
    tip: str | None = None

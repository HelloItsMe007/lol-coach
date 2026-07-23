"""Death-Analyse: pro Tod pruefen, ob er vermeidbar wirkte (isoliert, keine Vision)
oder Teil eines Teamfights war.

Limitierung (bewusst dokumentiert, nicht "weggemockt"):
- Teammate-Positionen stammen aus dem naechstgelegenen Timeline-Frame (alle 60s),
  nicht aus dem exakten Todeszeitpunkt - bei schnellen Rotationen kann das bis zu
  ~60s daneben liegen.
- Wir wissen nicht, ob ein Teammate zu diesem Zeitpunkt selbst schon tot war
  (kein Respawn-Tracking in dieser Version) - "nahe Verbuendete" kann daher in
  seltenen Faellen einen bereits toten Teammate mitzaehlen.
- "Vision vorhanden" wird nur ueber eigene WARD_PLACED-Events in Zeit-/Ortsnaehe
  approximiert, nicht ueber echten Fog-of-War-Status oder Ward-Restlebensdauer.
"""
from __future__ import annotations

from ..models import Finding, MatchContext, TimelineEvent

NEARBY_ALLY_RADIUS = 4000  # Map ist ca. 15000x15000; grobe Distanzeinheit
TEAMFIGHT_ALLY_COUNT = 2  # ab so vielen nahen Verbuendeten gilt es als Teamfight
VISION_RADIUS = 2500
VISION_LOOKBACK_MS = 90_000


def _own_team_recent_ward_nearby(
    ctx: MatchContext, team_id: int, death_ts_ms: int, death_pos
) -> bool:
    for frame in ctx.frames:
        for ev in frame.events:
            if ev.type != "WARD_PLACED" or ev.position is None:
                continue
            if not (death_ts_ms - VISION_LOOKBACK_MS <= ev.timestamp_ms <= death_ts_ms):
                continue
            creator = None
            if ev.creator_id is not None:
                try:
                    creator = ctx.participant_by_id(ev.creator_id)
                except KeyError:
                    creator = None
            if creator is not None and creator.team_id == team_id:
                if ev.position.distance_to(death_pos) <= VISION_RADIUS:
                    return True
    return False


def _nearby_ally_count(ctx: MatchContext, me_team_id: int, me_id: int, death_event: TimelineEvent) -> int:
    frame = ctx.frame_at_or_before(death_event.timestamp_ms)
    if frame is None or death_event.position is None:
        return 0
    count = 0
    for pid, pf in frame.participant_frames.items():
        if pid == me_id:
            continue
        try:
            p = ctx.participant_by_id(pid)
        except KeyError:
            continue
        if p.team_id != me_team_id:
            continue
        if pf.position.distance_to(death_event.position) <= NEARBY_ALLY_RADIUS:
            count += 1
    return count


def analyze_deaths(ctx: MatchContext, participant_id: int) -> list[Finding]:
    findings: list[Finding] = []
    me = ctx.participant_by_id(participant_id)

    death_events = [
        ev
        for frame in ctx.frames
        for ev in frame.events
        if ev.type == "CHAMPION_KILL" and ev.victim_id == participant_id
    ]

    isolated_no_vision_count = 0

    for ev in death_events:
        if ev.position is None:
            continue
        ally_count = _nearby_ally_count(ctx, me.team_id, participant_id, ev)
        killer_name = ""
        if ev.killer_id:
            try:
                killer_name = f" von {ctx.participant_by_id(ev.killer_id).champion_name}"
            except KeyError:
                pass

        if ally_count >= TEAMFIGHT_ALLY_COUNT:
            continue  # Teamfight-Tod, kein klares individuelles Fehlverhalten

        has_vision = _own_team_recent_ward_nearby(ctx, me.team_id, ev.timestamp_ms, ev.position)
        if not has_vision:
            isolated_no_vision_count += 1
            findings.append(
                Finding(
                    category="deaths",
                    valence="negative",
                    impact=5,
                    timestamp_s=ev.timestamp_s,
                    title="Vermeidbarer Tod: isoliert & ohne Vision",
                    description=(
                        f"Gestorben{killer_name}, {ally_count} Verbuendete in der Naehe, "
                        "keine eigene Ward in Zeit-/Ortsnaehe gefunden."
                    ),
                    tip="Vor dem Vorruecken in ungewardete Bereiche pruefen: Ist ein "
                    "Verbuendeter in Reichweite? Ist der Bereich gewardet?",
                )
            )
        else:
            findings.append(
                Finding(
                    category="deaths",
                    valence="negative",
                    impact=3,
                    timestamp_s=ev.timestamp_s,
                    title="Isolierter Tod trotz vorhandener Vision",
                    description=(
                        f"Gestorben{killer_name}, nur {ally_count} Verbuendete in der Naehe, "
                        "obwohl Vision vorhanden war."
                    ),
                    tip="Trotz Vision: Einschaetzung von Summoner-Spell-Cooldowns und "
                    "Kill-Potenzial des Gegners vor dem Engage/Trade schaerfen.",
                )
            )

    if isolated_no_vision_count >= 2:
        findings.append(
            Finding(
                category="deaths",
                valence="negative",
                impact=5,
                timestamp_s=0,
                title=f"Muster: {isolated_no_vision_count}x isoliert ohne Vision gestorben",
                description="Mehrere Tode diese Partie folgen dem gleichen Muster: "
                "allein unterwegs in ungewardeten Bereichen.",
                tip="Vor jeder Solo-Rotation kurz checken: Trinket-Cooldown genutzt? "
                "Letzte bekannte Gegnerpositionen beruecksichtigt?",
            )
        )

    return findings

"""Recall-Timing-Heuristik: laengere Phasen mit kritischer HP weit von der
eigenen Basis entfernt, die vermutlich einen frueheren Recall verdient haetten.

Datengrundlage: `championStats.health`/`healthMax` pro 60s-Frame (siehe
models.ParticipantFrame). Wichtige Einschraenkung: `health == 0` bedeutet in
den Rohdaten oft "Frame kurz nach dem Tod erfasst", nicht "lebend bei 0 HP" -
solche Frames werden hier bewusst uebersprungen statt als kritische Phase
gewertet. Es gibt kein echtes RECALL-Event in der Riot-Timeline; "an der Basis"
wird ueber eine grobe Distanz-Naeherung zur eigenen Fountain bestimmt.
"""
from __future__ import annotations

from ..models import Finding, MatchContext, Position

BASE_100 = Position(590, 1450)
BASE_200 = Position(14280, 13650)
BASE_RADIUS = 2500
LOW_HP_RATIO = 0.3


def _base_for_team(team_id: int) -> Position:
    return BASE_100 if team_id == 100 else BASE_200


def _finding_for_streak(streak_start_ms: int, streak_len_frames: int, frame_interval_ms: int) -> Finding:
    duration_s = int(streak_len_frames * frame_interval_ms / 1000)
    impact = 5 if streak_len_frames >= 3 else (4 if streak_len_frames == 2 else 3)
    return Finding(
        category="recall",
        valence="negative",
        impact=impact,
        timestamp_s=streak_start_ms // 1000,
        title="Recall vermutlich verpasst",
        description=(
            f"Mindestens {duration_s}s mit unter {int(LOW_HP_RATIO * 100)}% HP weit von der "
            "eigenen Basis entfernt unterwegs (naeherungsweise, 60s-Frame-Aufloesung)."
        ),
        tip="Bei kritischer HP frueher zurueckziehen/recallen, statt das Risiko weiter zu tragen.",
    )


def analyze_recall(ctx: MatchContext, participant_id: int) -> list[Finding]:
    findings: list[Finding] = []
    me = ctx.participant_by_id(participant_id)
    base = _base_for_team(me.team_id)

    streak_start_ms: int | None = None
    streak_len = 0

    for frame in sorted(ctx.frames, key=lambda f: f.timestamp_ms):
        pf = frame.participant_frames.get(participant_id)
        in_low_hp_streak = False
        if pf is not None and pf.health > 0:  # health==0 -> vermutlich Frame nach dem Tod
            ratio = pf.health_ratio
            if ratio is not None and ratio < LOW_HP_RATIO:
                distance = pf.position.distance_to(base)
                in_low_hp_streak = distance > BASE_RADIUS

        if in_low_hp_streak:
            if streak_start_ms is None:
                streak_start_ms = frame.timestamp_ms
            streak_len += 1
        else:
            if streak_start_ms is not None:
                findings.append(_finding_for_streak(streak_start_ms, streak_len, ctx.frame_interval_ms))
            streak_start_ms = None
            streak_len = 0

    if streak_start_ms is not None:
        findings.append(_finding_for_streak(streak_start_ms, streak_len, ctx.frame_interval_ms))

    return findings

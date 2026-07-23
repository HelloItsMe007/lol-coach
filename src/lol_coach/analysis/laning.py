"""Laning-Phase-Heuristiken (0-15 min): CS/min, Gold-/XP-Diff zum Lane-Gegner.

Limitierung: die CS/min-Richtwerte sind grobe Faustregeln, keine rollen- oder
patch-spezifisch kalibrierten Benchmarks. teamPosition kann bei manchen Matches
(z.B. Custom Games, sehr alte Matches) leer sein - dann werden Lane-Diff-Findings
uebersprungen statt geraten.
"""
from __future__ import annotations

from ..models import Finding, MatchContext

# grobe CS/min-Richtwerte je Rolle bei angemessenem Farmen
CS_PER_MIN_BENCHMARK = {
    "TOP": 7.0,
    "MIDDLE": 7.5,
    "BOTTOM": 7.5,
    "JUNGLE": 5.5,
    "UTILITY": 1.2,
}

CHECKPOINTS_MIN = (10, 15)
GOLD_DIFF_THRESHOLD = {10: 500, 15: 1000}
XP_DIFF_THRESHOLD = {10: 400, 15: 800}


def analyze_laning(ctx: MatchContext, participant_id: int) -> list[Finding]:
    findings: list[Finding] = []
    me = ctx.participant_by_id(participant_id)
    opponent = ctx.lane_opponent(participant_id)

    for minute in CHECKPOINTS_MIN:
        target_ms = minute * 60_000
        frame = ctx.frame_nearest(target_ms)
        if frame is None or participant_id not in frame.participant_frames:
            continue
        my_pf = frame.participant_frames[participant_id]

        benchmark = CS_PER_MIN_BENCHMARK.get(me.team_position)
        if benchmark is not None:
            cs_per_min = my_pf.total_cs / minute
            ratio = cs_per_min / benchmark
            if ratio < 0.8:
                findings.append(
                    Finding(
                        category="laning",
                        valence="negative",
                        impact=4 if ratio < 0.6 else 3,
                        timestamp_s=target_ms // 1000,
                        title=f"CS/min bei {minute} min unter Richtwert",
                        description=(
                            f"{cs_per_min:.1f} CS/min ({my_pf.total_cs} CS) vs. "
                            f"Richtwert ~{benchmark:.1f} fuer {me.team_position}."
                        ),
                        tip="Wave-Management und Last-Hitting priorisieren, "
                        "besonders wenn nicht aktiv unter Druck.",
                    )
                )
            elif ratio > 1.15:
                findings.append(
                    Finding(
                        category="laning",
                        valence="positive",
                        impact=2,
                        timestamp_s=target_ms // 1000,
                        title=f"Starkes Farmen bei {minute} min",
                        description=(
                            f"{cs_per_min:.1f} CS/min, deutlich ueber Richtwert "
                            f"~{benchmark:.1f} fuer {me.team_position}."
                        ),
                        tip=None,
                    )
                )

        if opponent is not None and opponent.participant_id in frame.participant_frames:
            opp_pf = frame.participant_frames[opponent.participant_id]
            gold_diff = my_pf.total_gold - opp_pf.total_gold
            xp_diff = my_pf.xp - opp_pf.xp

            gold_threshold = GOLD_DIFF_THRESHOLD[minute]
            if gold_diff <= -gold_threshold:
                findings.append(
                    Finding(
                        category="laning",
                        valence="negative",
                        impact=4 if gold_diff <= -1.5 * gold_threshold else 3,
                        timestamp_s=target_ms // 1000,
                        title=f"Gold-Rueckstand bei {minute} min",
                        description=(
                            f"{gold_diff} Gold Rueckstand auf {opponent.champion_name} "
                            f"({me.team_position})."
                        ),
                        tip="Trades/All-ins in dieser Lane vermeiden, bis der "
                        "Rueckstand aufgeholt ist; Wave nicht unnoetig pushen.",
                    )
                )
            elif gold_diff >= gold_threshold:
                findings.append(
                    Finding(
                        category="laning",
                        valence="positive",
                        impact=3,
                        timestamp_s=target_ms // 1000,
                        title=f"Gold-Vorsprung bei {minute} min",
                        description=(
                            f"+{gold_diff} Gold gegenueber {opponent.champion_name} "
                            f"({me.team_position})."
                        ),
                        tip="Vorsprung nutzen: Lane pushen und roamen/Objectives kontestieren.",
                    )
                )

            xp_threshold = XP_DIFF_THRESHOLD[minute]
            if xp_diff <= -xp_threshold:
                findings.append(
                    Finding(
                        category="laning",
                        valence="negative",
                        impact=2,
                        timestamp_s=target_ms // 1000,
                        title=f"XP-Rueckstand bei {minute} min",
                        description=f"{xp_diff} XP Rueckstand, Level-Nachteil moeglich.",
                        tip="Mehr Farm/Trades sichern, um Level-Nachteil in Skirmishes zu vermeiden.",
                    )
                )

    return findings

"""Vision-/Macro-Heuristiken auf Basis der finalen Match-Statistiken.

Limitierung: Vision Score, Wards Placed/Killed liegen nur als Gesamtwert fuer
die ganze Partie vor (nicht pro Zeitfenster), daher sind die Findings hier
nicht an einen exakten Zeitpunkt gebunden - sie werden mit timestamp_s=0
("gesamte Partie") einsortiert. Eine Aufschluesselung nach Spielphase waere
eine sinnvolle Erweiterung (aus WARD_PLACED/WARD_KILL-Timeline-Events).
"""
from __future__ import annotations

from ..models import Finding, MatchContext

# grobe Vision-Score/min-Richtwerte je Rolle
VISION_SCORE_PER_MIN_BENCHMARK = {
    "UTILITY": 2.0,
    "JUNGLE": 1.4,
    "TOP": 0.8,
    "MIDDLE": 0.8,
    "BOTTOM": 0.8,
}

WARDS_PLACED_PER_MIN_BENCHMARK = {
    "UTILITY": 1.5,
    "JUNGLE": 0.8,
    "TOP": 0.3,
    "MIDDLE": 0.3,
    "BOTTOM": 0.3,
}


def analyze_vision(ctx: MatchContext, participant_id: int) -> list[Finding]:
    findings: list[Finding] = []
    me = ctx.participant_by_id(participant_id)
    duration_min = max(ctx.game_duration_s / 60.0, 1.0)

    vision_benchmark = VISION_SCORE_PER_MIN_BENCHMARK.get(me.team_position)
    if vision_benchmark is not None:
        vision_per_min = me.vision_score / duration_min
        ratio = vision_per_min / vision_benchmark
        if ratio < 0.7:
            findings.append(
                Finding(
                    category="vision",
                    valence="negative",
                    impact=4 if ratio < 0.5 else 3,
                    timestamp_s=0,
                    title="Vision Score unter Richtwert (gesamte Partie)",
                    description=(
                        f"{vision_per_min:.2f} Vision Score/min ({me.vision_score} total) "
                        f"vs. Richtwert ~{vision_benchmark:.1f} fuer {me.team_position}."
                    ),
                    tip="Mehr Control Wards kaufen und in Fights/vor Objectives "
                    "aktiv Vision setzen bzw. gegnerische Wards clearen.",
                )
            )
        elif ratio > 1.3:
            findings.append(
                Finding(
                    category="vision",
                    valence="positive",
                    impact=2,
                    timestamp_s=0,
                    title="Starke Vision-Kontrolle",
                    description=(
                        f"{vision_per_min:.2f} Vision Score/min, deutlich ueber "
                        f"Richtwert ~{vision_benchmark:.1f}."
                    ),
                    tip=None,
                )
            )

    wards_benchmark = WARDS_PLACED_PER_MIN_BENCHMARK.get(me.team_position)
    if wards_benchmark is not None:
        wards_per_min = me.wards_placed / duration_min
        if wards_per_min < 0.5 * wards_benchmark:
            findings.append(
                Finding(
                    category="vision",
                    valence="negative",
                    impact=3,
                    timestamp_s=0,
                    title="Wenige Wards platziert (gesamte Partie)",
                    description=(
                        f"{me.wards_placed} Wards platziert ({wards_per_min:.2f}/min) "
                        f"vs. Richtwert ~{wards_benchmark:.1f}/min."
                    ),
                    tip="Trinket konsequent nutzen (Cooldown im Auge behalten) und "
                    "Control Wards fuer wichtige Kreuzungen/Objectives einplanen.",
                )
            )

    if me.wards_killed == 0 and duration_min > 15:
        findings.append(
            Finding(
                category="vision",
                valence="negative",
                impact=2,
                timestamp_s=0,
                title="Keine gegnerischen Wards zerstoert",
                description="0 Ward-Kills in einer Partie von "
                f"{duration_min:.0f} Minuten.",
                tip="Bei Rotationen/Backs gezielt bekannte Ward-Spots mit Pink "
                "Wards oder Sweeper clearen.",
            )
        )

    return findings

"""Aggregiert bereits berechnete Findings ueber mehrere Matches zu einem
Trend-Report. Keine neue Bewertungslogik - reine Aggregation der Ergebnisse aus
den bestehenden analyze_*-Funktionen (siehe deaths.py, laning.py, vision.py,
recall.py, ability_usage.py), die pro Match unveraendert weiterlaufen.

Negative/positive Findings werden pro Match nur nach Kategorie gezaehlt (nicht
nach Titel), um nicht bruechig gegenueber Formulierungsaenderungen in den
Findings zu werden.
"""
from __future__ import annotations

from dataclasses import dataclass

from ..models import Finding, MatchContext, Participant


@dataclass(frozen=True)
class MatchTrendRow:
    match_id: str
    game_creation_ms: int
    champion_name: str
    win: bool
    kills: int
    deaths: int
    assists: int
    cs_per_min: float
    vision_score_per_min: float
    negative_counts: dict[str, int]
    positive_counts: dict[str, int]


@dataclass(frozen=True)
class TrendReport:
    rows: tuple[MatchTrendRow, ...]  # chronologisch, aeltestes zuerst

    @property
    def win_rate(self) -> float:
        if not self.rows:
            return 0.0
        return sum(1 for r in self.rows if r.win) / len(self.rows)

    @property
    def avg_cs_per_min(self) -> float:
        if not self.rows:
            return 0.0
        return sum(r.cs_per_min for r in self.rows) / len(self.rows)

    @property
    def avg_vision_score_per_min(self) -> float:
        if not self.rows:
            return 0.0
        return sum(r.vision_score_per_min for r in self.rows) / len(self.rows)

    def total_negative_by_category(self) -> dict[str, int]:
        totals: dict[str, int] = {}
        for row in self.rows:
            for category, count in row.negative_counts.items():
                totals[category] = totals.get(category, 0) + count
        return totals


def _count_by_category(findings: list[Finding], valence: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for f in findings:
        if f.valence != valence:
            continue
        counts[f.category] = counts.get(f.category, 0) + 1
    return counts


def build_trend_report(
    entries: list[tuple[MatchContext, Participant, list[Finding]]],
) -> TrendReport:
    rows = []
    for ctx, participant, findings in entries:
        duration_min = max(ctx.game_duration_s / 60.0, 1.0)
        rows.append(
            MatchTrendRow(
                match_id=ctx.match_id,
                game_creation_ms=ctx.game_creation_ms,
                champion_name=participant.champion_name,
                win=participant.win,
                kills=participant.kills,
                deaths=participant.deaths,
                assists=participant.assists,
                cs_per_min=participant.total_cs / duration_min,
                vision_score_per_min=participant.vision_score / duration_min,
                negative_counts=_count_by_category(findings, "negative"),
                positive_counts=_count_by_category(findings, "positive"),
            )
        )
    rows.sort(key=lambda r: r.game_creation_ms)
    return TrendReport(rows=tuple(rows))

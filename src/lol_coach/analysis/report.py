"""Aggregiert Findings aus allen Analyse-Modulen zu einem priorisierten Report.

`organize_findings` ist die gemeinsame, reine Sortier-/Gruppierungslogik, die
sowohl vom CLI-Text-Report (`build_report`) als auch vom Web-Report
(`web/app.py` + `report.html`) genutzt wird - keine Duplikation zwischen den
beiden Ausgabeformaten.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from ..models import Finding, MatchContext


def format_timestamp(seconds: int) -> str:
    if seconds <= 0:
        return "gesamte Partie"
    m, s = divmod(seconds, 60)
    return f"{m:02d}:{s:02d}"


def format_date(game_creation_ms: int) -> str:
    """UTC-Datum, keine Anpassung an die Zeitzone des Betrachters (V1-Vereinfachung)."""
    if not game_creation_ms:
        return "unbekannt"
    dt = datetime.fromtimestamp(game_creation_ms / 1000, tz=timezone.utc)
    return dt.strftime("%d.%m.%Y %H:%M UTC")


@dataclass(frozen=True)
class OrganizedFindings:
    top_negatives: list[Finding]
    top_positives: list[Finding]
    chronological: list[Finding]


def organize_findings(findings: list[Finding]) -> OrganizedFindings:
    negatives = sorted(
        (f for f in findings if f.valence == "negative"), key=lambda f: f.impact, reverse=True
    )
    positives = sorted(
        (f for f in findings if f.valence == "positive"), key=lambda f: f.impact, reverse=True
    )
    chronological = sorted(findings, key=lambda f: f.timestamp_s)
    return OrganizedFindings(
        top_negatives=negatives[:3], top_positives=positives[:3], chronological=chronological
    )


def build_report(
    ctx: MatchContext,
    participant_id: int,
    findings: list[Finding],
    narrative: dict[str, str] | None = None,
) -> str:
    me = ctx.participant_by_id(participant_id)
    organized = organize_findings(findings)
    negatives = organized.top_negatives
    positives = organized.top_positives
    chronological = organized.chronological

    lines: list[str] = []
    lines.append("=" * 70)
    lines.append(
        f"Match {ctx.match_id} - {me.champion_name} ({me.team_position or '?'}) - "
        f"{'Sieg' if me.win else 'Niederlage'}"
    )
    lines.append(
        f"KDA {me.kills}/{me.deaths}/{me.assists} - CS {me.total_cs} - "
        f"Vision Score {me.vision_score} - Dauer {ctx.game_duration_s // 60} min"
    )
    lines.append("=" * 70)

    if narrative and narrative.get("intro"):
        lines.append("")
        lines.append(narrative["intro"])

    lines.append("")
    lines.append("TOP VERBESSERUNGSPUNKTE")
    lines.append("-" * 70)
    if negatives:
        for f in negatives:
            lines.append(f"[{format_timestamp(f.timestamp_s)}] (Impact {f.impact}/5) {f.title}")
            lines.append(f"    {f.description}")
            if f.tip:
                lines.append(f"    Tipp: {f.tip}")
    else:
        lines.append("Keine grossen Probleme erkannt.")

    lines.append("")
    lines.append("WAS GUT LIEF")
    lines.append("-" * 70)
    if positives:
        for f in positives:
            lines.append(f"[{format_timestamp(f.timestamp_s)}] {f.title}")
            lines.append(f"    {f.description}")
    else:
        lines.append("Keine auffaelligen Staerken erkannt.")

    lines.append("")
    lines.append("VOLLSTAENDIGE TIMELINE")
    lines.append("-" * 70)
    for f in chronological:
        sign = "+" if f.valence == "positive" else "-"
        lines.append(
            f"[{format_timestamp(f.timestamp_s)}] {sign} ({f.category}) {f.title}"
        )

    if narrative and narrative.get("conclusion"):
        lines.append("")
        lines.append("COACHING-FAZIT")
        lines.append("-" * 70)
        lines.append(narrative["conclusion"])

    lines.append("")
    if narrative:
        lines.append(
            "Hinweis: Die Findings/Zahlen oben basieren auf groben, regelbasierten "
            "Richtwerten (kein Video/CV). Das Intro/Fazit ist LLM-generiert auf Basis "
            "genau dieser Fakten und kann Kontext wie Cooldowns, Team-Absprachen oder "
            "Draft-Matchups nicht vollstaendig erfassen."
        )
    else:
        lines.append(
            "Hinweis: Alle Einschaetzungen basieren auf groben, regelbasierten Richtwerten "
            "(kein LLM, kein Video/CV) und koennen Kontext wie Cooldowns, Team-Absprachen "
            "oder Draft-Matchups nicht vollstaendig erfassen."
        )
    return "\n".join(lines)

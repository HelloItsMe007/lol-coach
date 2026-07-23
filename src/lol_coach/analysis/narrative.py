"""LLM-Narrativ-Layer: erzeugt ein kurzes Coaching-Intro + Fazit per Claude API,
auf Basis der bereits berechneten regelbasierten Findings.

Wichtig: die Findings (Zahlen, Zeitstempel, Klassifikationen) bleiben die Quelle
der Wahrheit. Claude bekommt sie als Fakten vorgegeben und formuliert nur einen
einordnenden Text - erfindet keine neuen Metriken und veraendert keine Werte.
Faellt der API-Call weg (kein Key, Netzwerkfehler, Rate-Limit), bleibt der
regelbasierte Report davon unberuehrt nutzbar (siehe cli.py).
"""
from __future__ import annotations

import anthropic

from ..models import Finding, MatchContext
from .trends import TrendReport

MODEL = "claude-sonnet-5"

SYSTEM_PROMPT = (
    "Du bist ein pragmatischer League-of-Legends-Coach. Du bekommst bereits "
    "berechnete, regelbasierte Fakten zu einer einzelnen Partie eines Spielers "
    "(Zahlen, Zeitstempel, Klassifikationen) sowie, wo vorhanden, die bestaetigte "
    "Ability-Reihenfolge (Q/W/E/R) in eigenen Todes-Kaempfen. Erfinde keine neuen "
    "Zahlen, keine Summoner-Spell-Aussagen (Flash etc. sind nicht in den Daten "
    "enthalten) und widersprich den gegebenen Fakten nicht. Kommentiere Ability-"
    "Reihenfolgen nur gehedged ('moeglicherweise', 'koennte') - die Sequenzen "
    "zeigen nur bestaetigt sichtbare Casts, keine vollstaendige Cast-Historie. "
    "Antworte auf Deutsch, in genau zwei Abschnitten, getrennt durch eine "
    "Leerzeile:\n"
    "1) 2-3 Saetze Einordnung, wie das Spiel insgesamt lief.\n"
    "2) 2-3 Saetze mit den wichtigsten naechsten Schritten, priorisiert nach Wirkung.\n"
    "Kein Praeambel, keine Ueberschriften, keine Aufzaehlungszeichen, kein Markdown."
)


def _build_prompt(
    ctx: MatchContext,
    participant_id: int,
    findings: list[Finding],
    combat_summaries: list[dict] | None = None,
) -> str:
    me = ctx.participant_by_id(participant_id)
    negatives = sorted(
        (f for f in findings if f.valence == "negative"), key=lambda f: f.impact, reverse=True
    )[:5]
    positives = sorted(
        (f for f in findings if f.valence == "positive"), key=lambda f: f.impact, reverse=True
    )[:3]

    lines = [
        f"Champion: {me.champion_name} ({me.team_position or 'unbekannte Rolle'})",
        f"Ergebnis: {'Sieg' if me.win else 'Niederlage'}",
        f"KDA: {me.kills}/{me.deaths}/{me.assists}, Dauer: {ctx.game_duration_s // 60} min",
        "",
        "Groesste Probleme (nach Wirkung sortiert):",
    ]
    lines += [f"- [{f.category}] {f.title}: {f.description}" for f in negatives] or ["- keine"]
    lines.append("")
    lines.append("Staerken:")
    lines += [f"- [{f.category}] {f.title}: {f.description}" for f in positives] or ["- keine"]

    if combat_summaries:
        lines.append("")
        lines.append(
            "Ability-Reihenfolge in eigenen Todes-Kaempfen (nur bestaetigt sichtbare "
            "Casts, keine vollstaendige Historie):"
        )
        for s in combat_summaries:
            own = "-".join(s["own_ability_sequence"]) or "keine sichtbar"
            enemy = "-".join(s["enemy_ability_sequence"]) or "keine sichtbar"
            gegner = s["killer_champion"] or "unbekannt"
            lines.append(
                f"- {s['timestamp_s'] // 60:02d}:{s['timestamp_s'] % 60:02d} gegen {gegner}: "
                f"eigene Reihenfolge [{own}], gegnerische Reihenfolge [{enemy}]"
            )

    return "\n".join(lines)


def _call_claude_two_paragraphs(
    client: anthropic.Anthropic, system_prompt: str, user_prompt: str
) -> dict[str, str]:
    response = client.messages.create(
        model=MODEL,
        max_tokens=1024,
        system=system_prompt,
        messages=[{"role": "user", "content": user_prompt}],
    )
    text_block = next((b for b in response.content if getattr(b, "type", None) == "text"), None)
    if text_block is None:
        raise RuntimeError("Keine Text-Antwort von Claude erhalten (nur Thinking-/Tool-Bloecke?)")
    text = text_block.text.strip()
    parts = text.split("\n\n", 1)
    intro = parts[0].strip()
    conclusion = parts[1].strip() if len(parts) > 1 else ""
    return {"intro": intro, "conclusion": conclusion}


def generate_narrative(
    client: anthropic.Anthropic,
    ctx: MatchContext,
    participant_id: int,
    findings: list[Finding],
    combat_summaries: list[dict] | None = None,
) -> dict[str, str]:
    prompt = _build_prompt(ctx, participant_id, findings, combat_summaries)
    return _call_claude_two_paragraphs(client, SYSTEM_PROMPT, prompt)


TREND_SYSTEM_PROMPT = (
    "Du bist ein pragmatischer League-of-Legends-Coach. Du bekommst bereits "
    "berechnete, regelbasierte Kennzahlen zu den letzten mehreren Partien eines "
    "Spielers: pro Partie Ergebnis, KDA, CS/min, Vision Score/min und die Anzahl "
    "negativer Findings je Kategorie (laning/vision/deaths/abilities/recall) - "
    "plus Durchschnittswerte und Summen ueber alle Partien. Die Kategorie-"
    "Zaehlungen sind grob (kein Titel-Detail pro Finding) - formuliere Aussagen "
    "dazu entsprechend vorsichtig gehedged. Erfinde keine neuen Zahlen und "
    "widersprich den gegebenen Fakten nicht. Antworte auf Deutsch, in genau zwei "
    "Abschnitten, getrennt durch eine Leerzeile:\n"
    "1) 2-3 Saetze Einordnung, welches Muster sich ueber die Partien zeigt (z.B. "
    "eine durchgehend dominante Kategorie, eine Verbesserung/Verschlechterung "
    "im zeitlichen Verlauf).\n"
    "2) 2-3 Saetze mit den wichtigsten naechsten Schritten, priorisiert nach Wirkung.\n"
    "Kein Praeambel, keine Ueberschriften, keine Aufzaehlungszeichen, kein Markdown."
)


def _build_trend_prompt(report: TrendReport) -> str:
    lines = [f"Verlauf der letzten {len(report.rows)} Partien (aeltestes zuerst):"]
    for row in report.rows:
        neg = ", ".join(f"{cat}: {count}" for cat, count in row.negative_counts.items()) or "keine"
        lines.append(
            f"- {row.champion_name}, {'Sieg' if row.win else 'Niederlage'}, "
            f"KDA {row.kills}/{row.deaths}/{row.assists}, CS/min {row.cs_per_min:.1f}, "
            f"Vision/min {row.vision_score_per_min:.2f}, negative Findings: {neg}"
        )

    totals = report.total_negative_by_category()
    totals_str = ", ".join(f"{cat}: {count}" for cat, count in totals.items()) or "keine"
    lines += [
        "",
        f"Win-Rate: {report.win_rate * 100:.0f}%",
        f"CS/min Durchschnitt: {report.avg_cs_per_min:.1f}",
        f"Vision Score/min Durchschnitt: {report.avg_vision_score_per_min:.2f}",
        f"Negative Findings insgesamt nach Kategorie: {totals_str}",
    ]
    return "\n".join(lines)


def generate_trend_narrative(client: anthropic.Anthropic, report: TrendReport) -> dict[str, str]:
    prompt = _build_trend_prompt(report)
    return _call_claude_two_paragraphs(client, TREND_SYSTEM_PROMPT, prompt)

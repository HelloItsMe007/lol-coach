"""Ability-Timing-Heuristik: war das Ultimate bei einem Tod vermutlich verfuegbar?
Zusaetzlich: Ability-Kombo-Sequenzen pro Tod (Q/W/E/R-Reihenfolge) als reine
Fakten fuer das LLM-Narrativ - keine Bewertung, die passiert bei Claude.

Die Ultimate-Verfuegbarkeits-Findings fokussieren bewusst nur auf Slot 3
(hoechster Impact, klarste Aussage). Die Kombo-Sequenzen (siehe
`death_combat_summaries`) decken dagegen alle vier Slots ab, liefern aber
bewusst keine Findings/Bewertung - nur geordnete Fakten, die der LLM-Layer
(narrative.py) taktisch einordnen kann, ohne eigene Zahlen erfinden zu muessen.

Datengrundlage (gegen echte Riot-Daten verifiziert, nicht angenommen):
- CHAMPION_KILL-Events liefern im Combat-Log (`victimDamageDealt`/
  `victimDamageReceived`) bestaetigte Zeitpunkte, an denen der Spieler eine
  Ability eingesetzt hat - aber NUR in Kaempfen, die mit einem Kill endeten.
  Reines Farmen/Poken ohne Kill-Abschluss ist unsichtbar. Deshalb werden alle
  Aussagen hier gehedged formuliert ("vermutlich", "laut sichtbaren Daten"),
  nie als Tatsachenbehauptung.
- SKILL_LEVEL_UP-Events liefern den Ability-Rang zu jedem Zeitpunkt
  (skillSlot 1-4 == spellSlot+1 aus dem Combat-Log).
- Cooldown-Werte pro Rang kommen von Data Dragon (siehe ddragon.py) und werden
  hier nur als Parameter entgegengenommen (kein Netzwerkzugriff in diesem Modul).
- Summoner Spells (Flash etc.) sind hier bewusst NICHT abgedeckt: Riots
  Timeline hat keinen Cast-Event dafuer, und Flash erzeugt keinen Schaden -
  taucht also auch nicht indirekt im Combat-Log auf (anders als z.B. Ignite,
  das als "summonerdot" im Log erscheint). Das ist eine harte API-Grenze.
"""
from __future__ import annotations

from ..models import Finding, MatchContext

CORE_SLOTS = (0, 1, 2, 3)  # Q, W, E, R
ULTIMATE_SLOT = 3
SLOT_LABELS = {0: "Q", 1: "W", 2: "E", 3: "R"}


def _confirmed_casts(ctx: MatchContext, participant_id: int) -> dict[int, list[int]]:
    casts: dict[int, list[int]] = {slot: [] for slot in CORE_SLOTS}
    for frame in ctx.frames:
        for ev in frame.events:
            if ev.type != "CHAMPION_KILL":
                continue
            if ev.victim_id == participant_id:
                for entry in ev.raw.get("victimDamageDealt", []):
                    slot = entry.get("spellSlot")
                    if slot in CORE_SLOTS:
                        casts[slot].append(ev.timestamp_ms)
            credited = set(ev.raw.get("assistingParticipantIds") or [])
            if ev.raw.get("killerId") is not None:
                credited.add(ev.raw["killerId"])
            if participant_id in credited:
                for entry in ev.raw.get("victimDamageReceived", []):
                    if entry.get("participantId") == participant_id:
                        slot = entry.get("spellSlot")
                        if slot in CORE_SLOTS:
                            casts[slot].append(ev.timestamp_ms)
    for slot in casts:
        casts[slot].sort()
    return casts


def _rank_at(ctx: MatchContext, participant_id: int, slot: int, timestamp_ms: int) -> int:
    rank = 0
    for frame in ctx.frames:
        for ev in frame.events:
            if ev.type != "SKILL_LEVEL_UP":
                continue
            if ev.raw.get("participantId") != participant_id:
                continue
            if ev.timestamp_ms > timestamp_ms:
                continue
            if ev.raw.get("skillSlot") == slot + 1:
                rank += 1
    return rank


def _effective_cooldown(cooldowns_for_slot: list[float], rank: int, ability_haste: int) -> float | None:
    if rank <= 0 or rank > len(cooldowns_for_slot):
        return None
    base_cd = cooldowns_for_slot[rank - 1]
    return base_cd * 100.0 / (100.0 + ability_haste)


def analyze_ability_usage(
    ctx: MatchContext, participant_id: int, cooldowns: list[list[float]]
) -> list[Finding]:
    findings: list[Finding] = []
    casts = _confirmed_casts(ctx, participant_id)
    ult_cooldowns = cooldowns[ULTIMATE_SLOT] if len(cooldowns) > ULTIMATE_SLOT else []

    death_events = [
        ev
        for frame in ctx.frames
        for ev in frame.events
        if ev.type == "CHAMPION_KILL" and ev.victim_id == participant_id
    ]

    for ev in death_events:
        death_ts = ev.timestamp_ms
        rank = _rank_at(ctx, participant_id, ULTIMATE_SLOT, death_ts)
        if rank <= 0:
            continue  # Ultimate noch nicht gelernt

        prior_casts = [t for t in casts[ULTIMATE_SLOT] if t < death_ts]

        frame = ctx.frame_nearest(death_ts)
        haste = 0
        if frame is not None and participant_id in frame.participant_frames:
            haste = frame.participant_frames[participant_id].ability_haste

        if not prior_casts:
            findings.append(
                Finding(
                    category="abilities",
                    valence="negative",
                    impact=3,
                    timestamp_s=ev.timestamp_s,
                    title="Ultimate nicht eingesetzt vor Tod",
                    description=(
                        "Laut Combat-Log wurde das Ultimate in dieser Partie bis zu "
                        "diesem Tod kein einziges Mal sichtbar eingesetzt."
                    ),
                    tip="Pruefen, ob das Ultimate in dieser Situation frueher haette "
                    "eingesetzt werden sollen (offensiv oder zur Flucht).",
                )
            )
            continue

        eff_cd = _effective_cooldown(ult_cooldowns, rank, haste)
        if eff_cd is None:
            continue

        last_cast = prior_casts[-1]
        elapsed_s = (death_ts - last_cast) / 1000.0
        if elapsed_s >= eff_cd:
            findings.append(
                Finding(
                    category="abilities",
                    valence="negative",
                    impact=3,
                    timestamp_s=ev.timestamp_s,
                    title="Ultimate vermutlich verfuegbar, aber nicht genutzt",
                    description=(
                        f"Letzter bestaetigter Ultimate-Einsatz {elapsed_s:.0f}s vor diesem "
                        f"Tod, errechneter Cooldown bei Rang {rank} ~{eff_cd:.0f}s - laut "
                        "sichtbaren Daten wahrscheinlich wieder verfuegbar gewesen."
                    ),
                    tip="Pruefen, ob das Ultimate hier defensiv oder offensiv haette "
                    "helfen koennen.",
                )
            )
        # sonst: rechnerisch noch on Cooldown -> keine echte Fehlentscheidung, kein Finding

    return findings


def _labeled_sequence(entries: list[dict]) -> list[str]:
    """Ordnet Combat-Log-Eintraege in Q/W/E/R-Labels (Reihenfolge = Array-Reihenfolge,
    die bei Riot der zeitlichen Reihenfolge innerhalb des Kampfes entspricht).
    Autoattacks/Passiv-Marker (nicht in SLOT_LABELS) werden herausgefiltert."""
    return [SLOT_LABELS[e["spellSlot"]] for e in entries if e.get("spellSlot") in SLOT_LABELS]


def death_combat_summaries(ctx: MatchContext, participant_id: int) -> list[dict]:
    """Pro eigenem Tod: welche eigenen und welche gegnerischen Abilities (Q/W/E/R)
    sind im Combat-Log bestaetigt aufgetaucht. Reine Fakten, keine Bewertung -
    gedacht als Input fuer narrative.py, nicht fuer eigene Findings (siehe Modul-
    Docstring: eine feste Kombo-Reihenfolge als "richtig/falsch" zu werten waere
    fuer >160 Champions nicht seriös per Hand kodierbar).
    """
    summaries: list[dict] = []
    for frame in ctx.frames:
        for ev in frame.events:
            if ev.type != "CHAMPION_KILL" or ev.victim_id != participant_id:
                continue
            own_sequence = _labeled_sequence(ev.raw.get("victimDamageDealt", []))
            enemy_sequence = _labeled_sequence(ev.raw.get("victimDamageReceived", []))
            killer_champion = None
            if ev.killer_id is not None:
                try:
                    killer_champion = ctx.participant_by_id(ev.killer_id).champion_name
                except KeyError:
                    killer_champion = None
            summaries.append(
                {
                    "timestamp_s": ev.timestamp_s,
                    "own_ability_sequence": own_sequence,
                    "enemy_ability_sequence": enemy_sequence,
                    "killer_champion": killer_champion,
                }
            )
    return summaries

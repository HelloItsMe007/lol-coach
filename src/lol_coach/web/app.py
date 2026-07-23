"""FastAPI-Website: duenne HTTP-Schicht ueber die bestehende Analyse-Pipeline.

Keine neue Analyse-Logik hier - `/analyze` ruft dieselben Funktionen auf wie
`cli.run_analyze` (siehe dort). Kein Login/Nutzerkonten noetig: Match-Verlauf
ist ueber Account-V1/Match-V5 oeffentlich abrufbar, sobald die App einen
gueltigen Riot-API-Key haelt (siehe README).
"""
from __future__ import annotations

import threading
from pathlib import Path

import anthropic
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, PlainTextResponse
from fastapi.templating import Jinja2Templates

from ..analysis.ability_usage import analyze_ability_usage, death_combat_summaries
from ..analysis.ddragon import get_ability_cooldowns, resolve_version
from ..analysis.deaths import analyze_deaths
from ..analysis.laning import analyze_laning
from ..analysis.narrative import generate_narrative
from ..analysis.recall import analyze_recall
from ..analysis.report import format_date, format_timestamp, organize_findings
from ..analysis.trends import build_trend_report
from ..analysis.vision import analyze_vision
from ..config import load_config
from ..fetch import fetch_match_context, get_recent_match_summaries, pick_match_id, resolve_puuid
from ..models import Finding, MatchContext
from ..riot_client import PLATFORM_TO_CONTINENT, RiotApiError, RiotClient

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
DEFAULT_REGION = "euw1"
RECENT_MATCH_COUNT = 10

app = FastAPI(title="LoL Post-Game Coach")
templates = Jinja2Templates(directory=str(TEMPLATES_DIR))
templates.env.filters["ts"] = format_timestamp
templates.env.filters["date"] = format_date

_config = load_config()
_anthropic_client = (
    anthropic.Anthropic(api_key=_config.anthropic_api_key) if _config.anthropic_api_key else None
)

# Riot-Ratenlimits gelten pro (API-Key, Region) - ein RiotClient pro Region,
# einmal erzeugt und wiederverwendet (nicht pro Request neu), damit der
# eingebaute RateLimiter (siehe riot_client.py) ueber alle Nutzer hinweg korrekt
# greift.
_riot_clients: dict[str, RiotClient] = {}
_riot_clients_lock = threading.Lock()


def _get_riot_client(region: str) -> RiotClient:
    with _riot_clients_lock:
        client = _riot_clients.get(region)
        if client is None:
            client = RiotClient(api_key=_config.riot_api_key, platform=region)
            _riot_clients[region] = client
        return client


# Riot-Ownership-Verifizierung fuer den Production-API-Key-Antrag (Register
# Product -> "Verify URL"). Der Wert ist kein Geheimnis, sondern soll oeffentlich
# unter /riot.txt abrufbar sein.
RIOT_VERIFICATION_TOKEN = "3b8a2b86-0ebf-43c9-9994-1ead433752a2"


@app.get("/riot.txt", response_class=PlainTextResponse)
def riot_verification() -> str:
    return RIOT_VERIFICATION_TOKEN


def _run_findings_pipeline(ctx: MatchContext, participant_id: int) -> tuple[list[Finding], str | None]:
    """Regelbasierte Analyse-Pipeline (ohne LLM-Narrativ) - von /analyze und
    /trends geteilt, damit beide garantiert dieselben Findings produzieren."""
    findings: list[Finding] = []
    findings += analyze_laning(ctx, participant_id)
    findings += analyze_vision(ctx, participant_id)
    findings += analyze_deaths(ctx, participant_id)
    findings += analyze_recall(ctx, participant_id)

    ability_warning = None
    try:
        champion_name = ctx.participant_by_id(participant_id).champion_name
        version = resolve_version(ctx.game_version)
        cooldowns = get_ability_cooldowns(champion_name, version)
        findings += analyze_ability_usage(ctx, participant_id, cooldowns)
    except Exception as exc:  # Netzwerk-/Parsing-Fehler duerfen den Report nie verhindern
        ability_warning = f"Ability-Cooldown-Analyse uebersprungen ({exc})"

    return findings, ability_warning


@app.get("/", response_class=HTMLResponse)
def index(request: Request):
    return templates.TemplateResponse(
        request,
        "index.html",
        {
            "regions": sorted(PLATFORM_TO_CONTINENT),
            "region": DEFAULT_REGION,
            "riot_id": "",
            "error": None,
        },
    )


@app.get("/analyze", response_class=HTMLResponse)
def analyze(request: Request, riot_id: str, region: str, match: str = "latest"):
    context = {
        "regions": sorted(PLATFORM_TO_CONTINENT),
        "riot_id": riot_id,
        "region": region,
        "error": None,
    }

    if "#" not in riot_id:
        context["error"] = "Riot-ID muss im Format 'Name#Tag' angegeben werden."
        return templates.TemplateResponse(request, "index.html", context)

    if region not in PLATFORM_TO_CONTINENT:
        context["error"] = f"Unbekannte Region '{region}'."
        return templates.TemplateResponse(request, "index.html", context)

    try:
        client = _get_riot_client(region)
        puuid = resolve_puuid(client, riot_id)
        match_id = pick_match_id(client, puuid, match)
        ctx = fetch_match_context(client, match_id)
        me = ctx.participant_by_puuid(puuid)
    except (RiotApiError, ValueError, RuntimeError, KeyError) as exc:
        context["error"] = str(exc).strip("'") or "Unbekannter Fehler bei der Analyse."
        return templates.TemplateResponse(request, "index.html", context)

    findings, ability_warning = _run_findings_pipeline(ctx, me.participant_id)

    narrative = None
    narrative_warning = None
    if _anthropic_client is not None:
        combat_summaries = death_combat_summaries(ctx, me.participant_id)
        try:
            narrative = generate_narrative(
                _anthropic_client, ctx, me.participant_id, findings, combat_summaries
            )
        except Exception as exc:  # Claude-Ausfall darf den Report nie verhindern
            narrative_warning = f"LLM-Narrativ konnte nicht erzeugt werden ({exc})"

    return templates.TemplateResponse(
        request,
        "report.html",
        {
            "riot_id": riot_id,
            "region": region,
            "ctx": ctx,
            "me": me,
            "organized": organize_findings(findings),
            "narrative": narrative,
            "ability_warning": ability_warning,
            "narrative_warning": narrative_warning,
        },
    )


@app.get("/matches", response_class=HTMLResponse)
def matches(request: Request, riot_id: str, region: str):
    context = {
        "regions": sorted(PLATFORM_TO_CONTINENT),
        "riot_id": riot_id,
        "region": region,
        "error": None,
    }

    if "#" not in riot_id:
        context["error"] = "Riot-ID muss im Format 'Name#Tag' angegeben werden."
        return templates.TemplateResponse(request, "index.html", context)

    if region not in PLATFORM_TO_CONTINENT:
        context["error"] = f"Unbekannte Region '{region}'."
        return templates.TemplateResponse(request, "index.html", context)

    try:
        client = _get_riot_client(region)
        puuid = resolve_puuid(client, riot_id)
        summaries = get_recent_match_summaries(client, puuid, count=RECENT_MATCH_COUNT)
    except (RiotApiError, ValueError, RuntimeError, KeyError) as exc:
        context["error"] = str(exc).strip("'") or "Unbekannter Fehler beim Laden der Matches."
        return templates.TemplateResponse(request, "index.html", context)

    if not summaries:
        context["error"] = "Keine Matches fuer diesen Account gefunden."
        return templates.TemplateResponse(request, "index.html", context)

    return templates.TemplateResponse(
        request,
        "matches.html",
        {"riot_id": riot_id, "region": region, "summaries": summaries},
    )


@app.get("/trends", response_class=HTMLResponse)
def trends(request: Request, riot_id: str, region: str):
    context = {
        "regions": sorted(PLATFORM_TO_CONTINENT),
        "riot_id": riot_id,
        "region": region,
        "error": None,
    }

    if "#" not in riot_id:
        context["error"] = "Riot-ID muss im Format 'Name#Tag' angegeben werden."
        return templates.TemplateResponse(request, "index.html", context)

    if region not in PLATFORM_TO_CONTINENT:
        context["error"] = f"Unbekannte Region '{region}'."
        return templates.TemplateResponse(request, "index.html", context)

    try:
        client = _get_riot_client(region)
        puuid = resolve_puuid(client, riot_id)
        match_ids = client.get_match_ids(puuid, count=RECENT_MATCH_COUNT)
    except (RiotApiError, ValueError, RuntimeError, KeyError) as exc:
        context["error"] = str(exc).strip("'") or "Unbekannter Fehler beim Laden der Matches."
        return templates.TemplateResponse(request, "index.html", context)

    if not match_ids:
        context["error"] = "Keine Matches fuer diesen Account gefunden."
        return templates.TemplateResponse(request, "index.html", context)

    entries = []
    for match_id in match_ids:
        try:
            ctx = fetch_match_context(client, match_id)
            me = ctx.participant_by_puuid(puuid)
        except (RiotApiError, KeyError):
            continue  # einzelnes fehlerhaftes Match ueberspringen, Rest bleibt nutzbar
        match_findings, _ability_warning = _run_findings_pipeline(ctx, me.participant_id)
        entries.append((ctx, me, match_findings))

    if not entries:
        context["error"] = "Keine auswertbaren Matches gefunden."
        return templates.TemplateResponse(request, "index.html", context)

    return templates.TemplateResponse(
        request,
        "trends.html",
        {"riot_id": riot_id, "region": region, "report": build_trend_report(entries)},
    )

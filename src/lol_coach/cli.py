from __future__ import annotations

import argparse
import sys

import anthropic

from .analysis.ability_usage import analyze_ability_usage, death_combat_summaries
from .analysis.ddragon import get_ability_cooldowns, resolve_version
from .analysis.deaths import analyze_deaths
from .analysis.laning import analyze_laning
from .analysis.narrative import generate_narrative
from .analysis.recall import analyze_recall
from .analysis.report import build_report
from .analysis.vision import analyze_vision
from .config import load_config
from .fetch import fetch_match_context, pick_match_id, resolve_puuid
from .riot_client import RiotClient


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(prog="lol_coach")
    sub = parser.add_subparsers(dest="command", required=True)

    analyze = sub.add_parser("analyze", help="Ein Match analysieren und Report ausgeben")
    analyze.add_argument("--riot-id", required=True, help="Riot-ID im Format Name#Tag")
    analyze.add_argument(
        "--region", required=True, help="Platform-Region, z.B. euw1, na1, kr"
    )
    analyze.add_argument(
        "--match",
        default="latest",
        help="'latest' fuer das letzte Match oder eine konkrete Match-ID",
    )
    return parser


def run_analyze(args: argparse.Namespace) -> int:
    config = load_config()
    client = RiotClient(api_key=config.riot_api_key, platform=args.region)

    puuid = resolve_puuid(client, args.riot_id)
    match_id = pick_match_id(client, puuid, args.match)
    ctx = fetch_match_context(client, match_id)

    try:
        me = ctx.participant_by_puuid(puuid)
    except KeyError:
        print("Dieser Account ist in diesem Match nicht als Teilnehmer gelistet.", file=sys.stderr)
        return 1

    findings = []
    findings += analyze_laning(ctx, me.participant_id)
    findings += analyze_vision(ctx, me.participant_id)
    findings += analyze_deaths(ctx, me.participant_id)
    findings += analyze_recall(ctx, me.participant_id)

    try:
        version = resolve_version(ctx.game_version)
        cooldowns = get_ability_cooldowns(me.champion_name, version)
        findings += analyze_ability_usage(ctx, me.participant_id, cooldowns)
    except Exception as exc:  # Netzwerk-/Parsing-Fehler duerfen den Report nie verhindern
        print(f"Hinweis: Ability-Cooldown-Analyse uebersprungen ({exc})", file=sys.stderr)

    narrative = None
    if config.anthropic_api_key:
        claude_client = anthropic.Anthropic(api_key=config.anthropic_api_key)
        combat_summaries = death_combat_summaries(ctx, me.participant_id)
        try:
            narrative = generate_narrative(
                claude_client, ctx, me.participant_id, findings, combat_summaries
            )
        except Exception as exc:  # Claude-Ausfall darf den regelbasierten Report nie verhindern
            print(f"Hinweis: LLM-Narrativ konnte nicht erzeugt werden ({exc})", file=sys.stderr)

    print(build_report(ctx, me.participant_id, findings, narrative=narrative))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_arg_parser()
    args = parser.parse_args(argv)
    if args.command == "analyze":
        return run_analyze(args)
    parser.print_help()
    return 1


if __name__ == "__main__":
    raise SystemExit(main())

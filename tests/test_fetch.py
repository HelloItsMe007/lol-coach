import json
from pathlib import Path

from lol_coach.fetch import parse_match_summary

FIXTURES = Path(__file__).parent / "fixtures"


def test_parse_match_summary_extracts_target_participant():
    match_json = json.loads((FIXTURES / "match.json").read_text())
    summary = parse_match_summary(match_json, "puuid-me")

    assert summary.match_id == "EUW1_1234567890"
    assert summary.champion_name == "Ahri"
    assert summary.team_position == "MIDDLE"
    assert summary.win is False
    assert summary.kills == 2
    assert summary.deaths == 2
    assert summary.assists == 3
    assert summary.game_duration_s == 1200


def test_parse_match_summary_unknown_puuid_raises_key_error():
    match_json = json.loads((FIXTURES / "match.json").read_text())
    try:
        parse_match_summary(match_json, "puuid-does-not-exist")
        assert False, "erwartete KeyError"
    except KeyError:
        pass

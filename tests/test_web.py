import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from lol_coach.fetch import parse_match_context
from lol_coach.models import MatchSummary
from lol_coach.web import app as app_module

FIXTURES = Path(__file__).parent / "fixtures"


def _fixture_ctx():
    match_json = json.loads((FIXTURES / "match.json").read_text())
    timeline_json = json.loads((FIXTURES / "timeline.json").read_text())
    return parse_match_context(match_json, timeline_json)


def _fake_resolve_version(game_version):
    raise RuntimeError("kein Netzwerk im Test")


def _fake_generate_narrative(client, ctx, participant_id, findings, combat_summaries=None):
    return {"intro": "TEST_INTRO", "conclusion": "TEST_FAZIT"}


class FakeRiotClient:
    def get_match_ids(self, puuid, count=1):
        return ["EUW1_1234567890"]


def _fake_get_recent_match_summaries(client, puuid, count=10):
    return [
        MatchSummary(
            match_id="EUW1_1234567890",
            game_creation_ms=1700000000000,
            game_duration_s=1200,
            champion_name="Ahri",
            team_position="MIDDLE",
            win=False,
            kills=2,
            deaths=5,
            assists=3,
        )
    ]


@pytest.fixture
def client(monkeypatch):
    # Keine echten Netzwerkaufrufe im Test: Riot-/Ddragon-/Claude-Aufrufe werden
    # durch feste Fakes ersetzt, unabhaengig davon was gerade in .env steht.
    monkeypatch.setattr(app_module, "resolve_puuid", lambda client, riot_id: "puuid-me")
    monkeypatch.setattr(
        app_module, "pick_match_id", lambda client, puuid, match: "EUW1_1234567890"
    )
    monkeypatch.setattr(
        app_module, "fetch_match_context", lambda client, match_id: _fixture_ctx()
    )
    monkeypatch.setattr(app_module, "resolve_version", _fake_resolve_version)
    monkeypatch.setattr(app_module, "_anthropic_client", object())
    monkeypatch.setattr(app_module, "generate_narrative", _fake_generate_narrative)
    monkeypatch.setattr(app_module, "_get_riot_client", lambda region: FakeRiotClient())
    monkeypatch.setattr(app_module, "get_recent_match_summaries", _fake_get_recent_match_summaries)
    return TestClient(app_module.app)


def test_index_returns_form(client):
    resp = client.get("/")
    assert resp.status_code == 200
    assert "Riot-ID" in resp.text


def test_analyze_renders_report_with_findings_and_narrative(client):
    resp = client.get("/analyze", params={"riot_id": "Test#EUW", "region": "euw1"})
    assert resp.status_code == 200
    assert "EUW1_1234567890" in resp.text
    assert "Ahri" in resp.text
    assert "Gold-Rueckstand bei 10 min" in resp.text
    assert "TEST_INTRO" in resp.text
    assert "TEST_FAZIT" in resp.text
    assert "Ability-Cooldown-Analyse uebersprungen" in resp.text


def test_analyze_rejects_invalid_riot_id(client):
    resp = client.get("/analyze", params={"riot_id": "NoHashHere", "region": "euw1"})
    assert resp.status_code == 200
    assert "Name#Tag" in resp.text


def test_analyze_rejects_unknown_region(client):
    resp = client.get("/analyze", params={"riot_id": "Test#EUW", "region": "mars1"})
    assert resp.status_code == 200
    assert "Unbekannte Region" in resp.text


def test_matches_lists_recent_matches(client):
    resp = client.get("/matches", params={"riot_id": "Test#EUW", "region": "euw1"})
    assert resp.status_code == 200
    assert "Ahri" in resp.text
    assert "EUW1_1234567890" in resp.text
    assert "Trend-Analyse" in resp.text


def test_matches_rejects_invalid_riot_id(client):
    resp = client.get("/matches", params={"riot_id": "NoHashHere", "region": "euw1"})
    assert resp.status_code == 200
    assert "Name#Tag" in resp.text


def test_trends_aggregates_across_matches(client):
    resp = client.get("/trends", params={"riot_id": "Test#EUW", "region": "euw1"})
    assert resp.status_code == 200
    assert "Trend ueber 1 Matches" in resp.text
    assert "Ahri" in resp.text
    assert "Zurueck zur Match-Liste" in resp.text

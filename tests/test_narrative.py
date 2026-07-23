from types import SimpleNamespace

from lol_coach.analysis.narrative import (
    _build_prompt,
    _build_trend_prompt,
    generate_narrative,
    generate_trend_narrative,
)
from lol_coach.analysis.report import build_report
from lol_coach.analysis.trends import MatchTrendRow, TrendReport
from lol_coach.models import Finding, MatchContext, Participant


def _minimal_ctx() -> MatchContext:
    participants = (
        Participant(1, "me", 100, "Ahri", "MIDDLE", False, 2, 5, 3, 90, 12, 2, 0, 6000),
    )
    return MatchContext(
        match_id="TEST_NARRATIVE",
        game_duration_s=1500,
        frame_interval_ms=60000,
        participants=participants,
        frames=(),
    )


class FakeMessages:
    def __init__(self, text: str, with_thinking_block: bool = False):
        self._text = text
        self._with_thinking_block = with_thinking_block

    def create(self, **kwargs):
        content = []
        if self._with_thinking_block:
            content.append(SimpleNamespace(type="thinking", thinking="..."))
        content.append(SimpleNamespace(type="text", text=self._text))
        return SimpleNamespace(content=content)


class FakeClient:
    def __init__(self, text: str, with_thinking_block: bool = False):
        self.messages = FakeMessages(text, with_thinking_block)


def test_build_prompt_includes_findings():
    ctx = _minimal_ctx()
    findings = [
        Finding("laning", "negative", 4, 600, "Gold-Rueckstand bei 10 min", "beschreibung", "tipp"),
        Finding("laning", "positive", 2, 900, "Starkes Farmen bei 15 min", "beschreibung", None),
    ]
    prompt = _build_prompt(ctx, 1, findings)
    assert "Gold-Rueckstand bei 10 min" in prompt
    assert "Starkes Farmen bei 15 min" in prompt
    assert "Ahri" in prompt
    assert "Niederlage" in prompt


def test_build_prompt_includes_combat_summaries():
    ctx = _minimal_ctx()
    combat_summaries = [
        {
            "timestamp_s": 125,
            "own_ability_sequence": ["Q", "E"],
            "enemy_ability_sequence": ["Q", "W", "R"],
            "killer_champion": "Yasuo",
        }
    ]
    prompt = _build_prompt(ctx, 1, [], combat_summaries=combat_summaries)
    assert "Yasuo" in prompt
    assert "[Q-E]" in prompt
    assert "[Q-W-R]" in prompt


def test_generate_narrative_splits_intro_and_conclusion():
    ctx = _minimal_ctx()
    fake_client = FakeClient("Das Spiel lief schwierig.\n\nFokussiere zuerst auf Vision.")
    result = generate_narrative(fake_client, ctx, 1, [])
    assert result["intro"] == "Das Spiel lief schwierig."
    assert result["conclusion"] == "Fokussiere zuerst auf Vision."


def test_generate_narrative_skips_leading_thinking_block():
    # Regression-Test: Claude Sonnet 5 kann einen Thinking-Block als erstes
    # content-Element liefern - response.content[0] waere dann kein Textblock.
    ctx = _minimal_ctx()
    fake_client = FakeClient(
        "Das Spiel lief schwierig.\n\nFokussiere zuerst auf Vision.", with_thinking_block=True
    )
    result = generate_narrative(fake_client, ctx, 1, [])
    assert result["intro"] == "Das Spiel lief schwierig."


def test_generate_narrative_handles_missing_conclusion():
    ctx = _minimal_ctx()
    fake_client = FakeClient("Nur ein einzelner Absatz ohne Trennung.")
    result = generate_narrative(fake_client, ctx, 1, [])
    assert result["intro"] == "Nur ein einzelner Absatz ohne Trennung."
    assert result["conclusion"] == ""


def _sample_trend_report() -> TrendReport:
    rows = (
        MatchTrendRow(
            match_id="A", game_creation_ms=1000, champion_name="Xerath", win=False,
            kills=2, deaths=6, assists=3, cs_per_min=3.0, vision_score_per_min=1.2,
            negative_counts={"deaths": 4, "vision": 1}, positive_counts={},
        ),
        MatchTrendRow(
            match_id="B", game_creation_ms=2000, champion_name="Xerath", win=True,
            kills=8, deaths=2, assists=9, cs_per_min=4.5, vision_score_per_min=1.8,
            negative_counts={"deaths": 1}, positive_counts={"laning": 2},
        ),
    )
    return TrendReport(rows=rows)


def test_build_trend_prompt_includes_per_match_and_summary_stats():
    report = _sample_trend_report()
    prompt = _build_trend_prompt(report)
    assert "Xerath" in prompt
    assert "deaths: 4" in prompt
    assert "Win-Rate: 50%" in prompt
    assert "deaths: 5" in prompt  # Summe ueber beide Matches (4+1)


def test_generate_trend_narrative_splits_intro_and_conclusion():
    report = _sample_trend_report()
    fake_client = FakeClient("Deaths sind das wiederkehrende Problem.\n\nFokussiere auf Vision.")
    result = generate_trend_narrative(fake_client, report)
    assert result["intro"] == "Deaths sind das wiederkehrende Problem."
    assert result["conclusion"] == "Fokussiere auf Vision."


def test_build_report_embeds_narrative_when_present():
    ctx = _minimal_ctx()
    report_with = build_report(ctx, 1, [], narrative={"intro": "INTRO_TEXT", "conclusion": "FAZIT_TEXT"})
    assert "INTRO_TEXT" in report_with
    assert "COACHING-FAZIT" in report_with
    assert "FAZIT_TEXT" in report_with

    report_without = build_report(ctx, 1, [], narrative=None)
    assert "INTRO_TEXT" not in report_without
    assert "COACHING-FAZIT" not in report_without

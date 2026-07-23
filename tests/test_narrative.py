from types import SimpleNamespace

from lol_coach.analysis.narrative import _build_prompt, generate_narrative
from lol_coach.analysis.report import build_report
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


def test_build_report_embeds_narrative_when_present():
    ctx = _minimal_ctx()
    report_with = build_report(ctx, 1, [], narrative={"intro": "INTRO_TEXT", "conclusion": "FAZIT_TEXT"})
    assert "INTRO_TEXT" in report_with
    assert "COACHING-FAZIT" in report_with
    assert "FAZIT_TEXT" in report_with

    report_without = build_report(ctx, 1, [], narrative=None)
    assert "INTRO_TEXT" not in report_without
    assert "COACHING-FAZIT" not in report_without

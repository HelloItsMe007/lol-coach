import json
from pathlib import Path

from lol_coach.analysis.deaths import analyze_deaths
from lol_coach.analysis.laning import analyze_laning
from lol_coach.analysis.report import build_report
from lol_coach.analysis.vision import analyze_vision
from lol_coach.fetch import parse_match_context
from lol_coach.models import Frame, MatchContext, Participant, ParticipantFrame, Position, TimelineEvent

FIXTURES = Path(__file__).parent / "fixtures"


def load_fixture_ctx() -> MatchContext:
    match_json = json.loads((FIXTURES / "match.json").read_text())
    timeline_json = json.loads((FIXTURES / "timeline.json").read_text())
    return parse_match_context(match_json, timeline_json)


def titles(findings):
    return {f.title for f in findings}


def test_full_match_report_flags_losing_lane_and_deaths():
    ctx = load_fixture_ctx()
    me = ctx.participant_by_puuid("puuid-me")
    assert me.participant_id == 1

    laning_findings = analyze_laning(ctx, me.participant_id)
    vision_findings = analyze_vision(ctx, me.participant_id)
    death_findings = analyze_deaths(ctx, me.participant_id)

    laning_titles = titles(laning_findings)
    assert "CS/min bei 10 min unter Richtwert" in laning_titles
    assert "CS/min bei 15 min unter Richtwert" in laning_titles
    assert "Gold-Rueckstand bei 10 min" in laning_titles
    assert "Gold-Rueckstand bei 15 min" in laning_titles
    assert "XP-Rueckstand bei 10 min" in laning_titles
    assert not any(f.valence == "positive" for f in laning_findings)

    vision_titles = titles(vision_findings)
    assert "Vision Score unter Richtwert (gesamte Partie)" in vision_titles
    assert "Wenige Wards platziert (gesamte Partie)" in vision_titles
    assert "Keine gegnerischen Wards zerstoert" in vision_titles

    death_titles = titles(death_findings)
    assert "Vermeidbarer Tod: isoliert & ohne Vision" in death_titles
    assert "Isolierter Tod trotz vorhandener Vision" in death_titles
    # nur 1x "isoliert ohne Vision" -> Muster-Finding darf noch nicht ausloesen
    assert not any(f.title.startswith("Muster:") for f in death_findings)

    all_findings = laning_findings + vision_findings + death_findings
    report = build_report(ctx, me.participant_id, all_findings)
    assert "EUW1_1234567890" in report
    assert "TOP VERBESSERUNGSPUNKTE" in report
    assert "VOLLSTAENDIGE TIMELINE" in report


def _pf(participant_id, x, y, **kwargs):
    defaults = dict(current_gold=0, total_gold=0, level=1, xp=0, minions_killed=0, jungle_minions_killed=0)
    defaults.update(kwargs)
    return ParticipantFrame(participant_id=participant_id, position=Position(x, y), **defaults)


def test_teamfight_death_is_not_flagged_as_isolated():
    participants = (
        Participant(1, "me", 100, "Ahri", "MIDDLE", False, 0, 1, 0, 0, 0, 0, 0, 0),
        Participant(2, "ally1", 100, "Garen", "TOP", False, 0, 0, 0, 0, 0, 0, 0, 0),
        Participant(5, "ally2", 100, "Nami", "UTILITY", False, 0, 0, 0, 0, 0, 0, 0, 0),
        Participant(3, "opp", 200, "Zed", "MIDDLE", True, 1, 0, 0, 0, 0, 0, 0, 0),
    )
    death_event = TimelineEvent(
        type="CHAMPION_KILL",
        timestamp_ms=100_000,
        killer_id=3,
        victim_id=1,
        position=Position(5000, 5000),
    )
    frame = Frame(
        timestamp_ms=100_000,
        participant_frames={
            1: _pf(1, 5000, 5000),
            2: _pf(2, 5000, 4000),  # distance 1000 -> nearby
            5: _pf(5, 4000, 5000),  # distance 1000 -> nearby
            3: _pf(3, 5000, 5000),
        },
        events=(death_event,),
    )
    ctx = MatchContext(
        match_id="TEST_1",
        game_duration_s=600,
        frame_interval_ms=60000,
        participants=participants,
        frames=(frame,),
    )
    findings = analyze_deaths(ctx, 1)
    assert findings == []  # 2 Verbuendete in der Naehe -> Teamfight, kein Mistake-Finding


def test_laning_flags_positive_findings_when_ahead():
    participants = (
        Participant(1, "me", 100, "Ahri", "MIDDLE", True, 0, 0, 0, 0, 0, 0, 0, 0),
        Participant(3, "opp", 200, "Zed", "MIDDLE", False, 0, 0, 0, 0, 0, 0, 0, 0),
    )
    frame = Frame(
        timestamp_ms=600_000,
        participant_frames={
            1: _pf(1, 0, 0, total_gold=5000, xp=1000, minions_killed=100),
            3: _pf(3, 0, 0, total_gold=3000, xp=800, minions_killed=50),
        },
        events=(),
    )
    ctx = MatchContext(
        match_id="TEST_2",
        game_duration_s=900,
        frame_interval_ms=60000,
        participants=participants,
        frames=(frame,),
    )
    findings = analyze_laning(ctx, 1)
    found_titles = titles(findings)
    assert "Starkes Farmen bei 10 min" in found_titles
    assert "Gold-Vorsprung bei 10 min" in found_titles

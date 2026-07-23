from lol_coach.analysis.recall import analyze_recall
from lol_coach.models import Frame, MatchContext, Participant, ParticipantFrame, Position


def _participant(team_id=100):
    return Participant(1, "me", team_id, "Xerath", "UTILITY", False, 0, 0, 0, 0, 0, 0, 0, 0)


def _pf(x, y, health, health_max):
    return ParticipantFrame(
        participant_id=1,
        position=Position(x, y),
        current_gold=0,
        total_gold=0,
        level=6,
        xp=0,
        minions_killed=0,
        jungle_minions_killed=0,
        health=health,
        health_max=health_max,
    )


def test_sustained_low_hp_far_from_base_flags_finding():
    frames = (
        Frame(0, {1: _pf(600, 1450, 1000, 1000)}, ()),  # gesund, an der Basis
        Frame(60_000, {1: _pf(8000, 8000, 100, 1000)}, ()),  # 10% HP, weit weg -> Streak Start
        Frame(120_000, {1: _pf(8000, 8000, 120, 1000)}, ()),  # weiterhin kritisch
        Frame(180_000, {1: _pf(8000, 8000, 900, 1000)}, ()),  # geheilt/zurueck -> Streak endet
    )
    ctx = MatchContext(
        match_id="R1", game_duration_s=600, frame_interval_ms=60000,
        participants=(_participant(),), frames=frames,
    )
    findings = analyze_recall(ctx, 1)
    assert len(findings) == 1
    assert findings[0].title == "Recall vermutlich verpasst"
    assert findings[0].timestamp_s == 60
    assert findings[0].impact == 4  # 2 Frames Streak-Laenge


def test_low_hp_near_base_is_not_flagged():
    frames = (
        Frame(0, {1: _pf(600, 1450, 100, 1000)}, ()),  # kritisch, aber an der Basis
    )
    ctx = MatchContext(
        match_id="R2", game_duration_s=600, frame_interval_ms=60000,
        participants=(_participant(),), frames=frames,
    )
    assert analyze_recall(ctx, 1) == []


def test_zero_health_frame_is_treated_as_post_death_not_low_hp():
    frames = (
        Frame(0, {1: _pf(8000, 8000, 0, 1000)}, ()),  # vermutlich Frame nach dem Tod
    )
    ctx = MatchContext(
        match_id="R3", game_duration_s=600, frame_interval_ms=60000,
        participants=(_participant(),), frames=frames,
    )
    assert analyze_recall(ctx, 1) == []


def test_team_200_uses_its_own_base():
    frames = (
        Frame(0, {1: _pf(14280, 13650, 100, 1000)}, ()),  # kritisch, an der eigenen (roten) Basis
    )
    ctx = MatchContext(
        match_id="R4", game_duration_s=600, frame_interval_ms=60000,
        participants=(_participant(team_id=200),), frames=frames,
    )
    assert analyze_recall(ctx, 1) == []

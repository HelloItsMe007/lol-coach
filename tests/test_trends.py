from lol_coach.analysis.trends import build_trend_report
from lol_coach.models import Finding, MatchContext, Participant


def _ctx(match_id, game_creation_ms, duration_s=1200):
    return MatchContext(
        match_id=match_id,
        game_duration_s=duration_s,
        frame_interval_ms=60000,
        participants=(),
        frames=(),
        game_creation_ms=game_creation_ms,
    )


def _participant(champion_name, win, kills, deaths, assists, total_cs=100, vision_score=20):
    return Participant(
        1, "puuid-me", 100, champion_name, "MIDDLE", win, kills, deaths, assists,
        total_cs, vision_score, 0, 0, 0,
    )


def test_build_trend_report_sorts_chronologically_and_computes_averages():
    match_a = (
        _ctx("A", game_creation_ms=2000),
        _participant("Ahri", win=True, kills=5, deaths=1, assists=3, total_cs=200, vision_score=40),
        [Finding("laning", "positive", 3, 100, "Starkes Farmen", "desc")],
    )
    match_b = (
        _ctx("B", game_creation_ms=1000),
        _participant("Ahri", win=False, kills=1, deaths=6, assists=2, total_cs=100, vision_score=20),
        [
            Finding("deaths", "negative", 5, 200, "Vermeidbarer Tod", "desc"),
            Finding("deaths", "negative", 5, 300, "Vermeidbarer Tod", "desc"),
            Finding("vision", "negative", 3, 0, "Wenige Wards", "desc"),
        ],
    )

    report = build_trend_report([match_a, match_b])

    # chronologisch: B (2000ms... nein 1000ms) zuerst, dann A (2000ms)
    assert [row.match_id for row in report.rows] == ["B", "A"]
    assert report.win_rate == 0.5

    # CS/min: A=200/20min=10.0, B=100/20min=5.0 -> avg=7.5
    assert report.avg_cs_per_min == 7.5

    totals = report.total_negative_by_category()
    assert totals == {"deaths": 2, "vision": 1}


def test_build_trend_report_empty_list():
    report = build_trend_report([])
    assert report.rows == ()
    assert report.win_rate == 0.0
    assert report.avg_cs_per_min == 0.0
    assert report.total_negative_by_category() == {}

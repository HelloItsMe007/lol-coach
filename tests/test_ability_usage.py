from lol_coach.analysis.ability_usage import analyze_ability_usage, death_combat_summaries
from lol_coach.models import Frame, MatchContext, Participant, ParticipantFrame, Position, TimelineEvent

# Grobe Xerath-aehnliche Cooldown-Tabelle: slot 0=Q,1=W,2=E,3=R (Rang-Index 0-basiert)
COOLDOWNS = [
    [9, 8, 7, 6, 5],
    [14, 13, 12, 11, 10],
    [13, 12.5, 12, 11.5, 11],
    [130, 115, 100],
]


def _participant(participant_id=1):
    return Participant(participant_id, "me", 100, "Xerath", "UTILITY", False, 0, 0, 0, 0, 0, 0, 0, 0)


def _skill_level_up(timestamp_ms, skill_slot, participant_id=1):
    return TimelineEvent(
        type="SKILL_LEVEL_UP",
        timestamp_ms=timestamp_ms,
        raw={
            "type": "SKILL_LEVEL_UP",
            "timestamp": timestamp_ms,
            "participantId": participant_id,
            "skillSlot": skill_slot,
            "levelUpType": "NORMAL",
        },
    )


def _own_death(timestamp_ms, victim_id=1, killer_id=2, dealt_slots=()):
    dealt = [{"participantId": victim_id, "spellSlot": slot, "spellName": f"slot{slot}"} for slot in dealt_slots]
    return TimelineEvent(
        type="CHAMPION_KILL",
        timestamp_ms=timestamp_ms,
        victim_id=victim_id,
        killer_id=killer_id,
        raw={
            "type": "CHAMPION_KILL",
            "timestamp": timestamp_ms,
            "victimId": victim_id,
            "killerId": killer_id,
            "assistingParticipantIds": [],
            "victimDamageDealt": dealt,
            "victimDamageReceived": [],
        },
    )


def _own_kill_credit(timestamp_ms, other_victim_id, dealt_slot_by_me):
    # unser Spieler (id=1) ist killer eines anderen Teilnehmers -> eigener Cast
    # taucht in victimDamageReceived des Opfers auf, participantId==1
    return TimelineEvent(
        type="CHAMPION_KILL",
        timestamp_ms=timestamp_ms,
        victim_id=other_victim_id,
        killer_id=1,
        raw={
            "type": "CHAMPION_KILL",
            "timestamp": timestamp_ms,
            "victimId": other_victim_id,
            "killerId": 1,
            "assistingParticipantIds": [],
            "victimDamageDealt": [],
            "victimDamageReceived": [{"participantId": 1, "spellSlot": dealt_slot_by_me, "spellName": "ult"}],
        },
    )


def _empty_frame(timestamp_ms, participant_id=1):
    return Frame(
        timestamp_ms=timestamp_ms,
        participant_frames={
            participant_id: ParticipantFrame(
                participant_id=participant_id,
                position=Position(0, 0),
                current_gold=0,
                total_gold=0,
                level=6,
                xp=0,
                minions_killed=0,
                jungle_minions_killed=0,
                ability_haste=0,
            )
        },
        events=(),
    )


def test_ultimate_never_cast_flags_finding():
    ult_learned = _skill_level_up(60_000, skill_slot=4)
    death = _own_death(300_000, dealt_slots=(0, 1))  # Q und W genutzt, kein Ultimate (slot 3)
    ctx = MatchContext(
        match_id="T1",
        game_duration_s=600,
        frame_interval_ms=60000,
        participants=(_participant(),),
        frames=(_empty_frame(0), Frame(60_000, {1: _empty_frame(60_000).participant_frames[1]}, (ult_learned,)),
                Frame(300_000, {1: _empty_frame(300_000).participant_frames[1]}, (death,))),
    )
    findings = analyze_ability_usage(ctx, 1, COOLDOWNS)
    assert any(f.title == "Ultimate nicht eingesetzt vor Tod" for f in findings)


def test_ultimate_available_again_flags_finding():
    ult_learned = _skill_level_up(60_000, skill_slot=4)
    last_ult_cast = _own_kill_credit(100_000, other_victim_id=9, dealt_slot_by_me=3)
    death = _own_death(300_000)  # 200s nach letztem Ult-Einsatz, Rang-1-CD ist 130s -> sollte verfuegbar sein
    ctx = MatchContext(
        match_id="T2",
        game_duration_s=600,
        frame_interval_ms=60000,
        participants=(_participant(),),
        frames=(
            Frame(60_000, {1: _empty_frame(60_000).participant_frames[1]}, (ult_learned,)),
            Frame(100_000, {1: _empty_frame(100_000).participant_frames[1]}, (last_ult_cast,)),
            Frame(300_000, {1: _empty_frame(300_000).participant_frames[1]}, (death,)),
        ),
    )
    findings = analyze_ability_usage(ctx, 1, COOLDOWNS)
    assert any(f.title == "Ultimate vermutlich verfuegbar, aber nicht genutzt" for f in findings)


def test_ultimate_still_on_cooldown_no_finding():
    ult_learned = _skill_level_up(60_000, skill_slot=4)
    last_ult_cast = _own_kill_credit(290_000, other_victim_id=9, dealt_slot_by_me=3)
    death = _own_death(300_000)  # nur 10s spaeter, Rang-1-CD 130s -> eindeutig noch on CD
    ctx = MatchContext(
        match_id="T3",
        game_duration_s=600,
        frame_interval_ms=60000,
        participants=(_participant(),),
        frames=(
            Frame(60_000, {1: _empty_frame(60_000).participant_frames[1]}, (ult_learned,)),
            Frame(290_000, {1: _empty_frame(290_000).participant_frames[1]}, (last_ult_cast,)),
            Frame(300_000, {1: _empty_frame(300_000).participant_frames[1]}, (death,)),
        ),
    )
    findings = analyze_ability_usage(ctx, 1, COOLDOWNS)
    assert findings == []


def test_ultimate_not_yet_learned_no_finding():
    death = _own_death(60_000)  # kein SKILL_LEVEL_UP fuer Slot 4 vorher -> Rang 0
    ctx = MatchContext(
        match_id="T4",
        game_duration_s=600,
        frame_interval_ms=60000,
        participants=(_participant(),),
        frames=(Frame(60_000, {1: _empty_frame(60_000).participant_frames[1]}, (death,)),),
    )
    findings = analyze_ability_usage(ctx, 1, COOLDOWNS)
    assert findings == []


def test_death_combat_summaries_extracts_own_and_enemy_sequence():
    death = TimelineEvent(
        type="CHAMPION_KILL",
        timestamp_ms=125_000,
        victim_id=1,
        killer_id=2,
        raw={
            "type": "CHAMPION_KILL",
            "timestamp": 125_000,
            "victimId": 1,
            "killerId": 2,
            "assistingParticipantIds": [],
            "victimDamageDealt": [
                {"participantId": 2, "spellSlot": 0, "spellName": "q"},
                {"participantId": 2, "spellSlot": 2, "spellName": "e"},
                {"participantId": 2, "spellSlot": 49, "spellName": "autoattack"},
            ],
            "victimDamageReceived": [
                {"participantId": 2, "spellSlot": 0, "spellName": "enemyq"},
                {"participantId": 2, "spellSlot": 1, "spellName": "enemyw"},
                {"participantId": 2, "spellSlot": 3, "spellName": "enemyr"},
            ],
        },
    )
    killer = Participant(2, "them", 200, "Yasuo", "TOP", True, 0, 0, 0, 0, 0, 0, 0, 0)
    ctx = MatchContext(
        match_id="T5",
        game_duration_s=600,
        frame_interval_ms=60000,
        participants=(_participant(), killer),
        frames=(Frame(125_000, {}, (death,)),),
    )
    summaries = death_combat_summaries(ctx, 1)
    assert len(summaries) == 1
    assert summaries[0]["timestamp_s"] == 125
    assert summaries[0]["own_ability_sequence"] == ["Q", "E"]
    assert summaries[0]["enemy_ability_sequence"] == ["Q", "W", "R"]
    assert summaries[0]["killer_champion"] == "Yasuo"

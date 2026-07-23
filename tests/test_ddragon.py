import pytest

from lol_coach.analysis import ddragon

VERSIONS = ["16.14.1", "16.2.1", "16.1.1"]
XERATH_DATA = {
    "data": {
        "Xerath": {
            "spells": [
                {"cooldown": [9, 8, 7, 6, 5]},
                {"cooldown": [14, 13, 12, 11, 10]},
                {"cooldown": [13, 12.5, 12, 11.5, 11]},
                {"cooldown": [130, 115, 100]},
            ]
        }
    }
}


class FakeResponse:
    def __init__(self, data, ok=True, status_code=200):
        self._data = data
        self.ok = ok
        self.status_code = status_code

    def json(self):
        return self._data


def _fake_get(url, timeout=10):
    if url.endswith("versions.json"):
        return FakeResponse(VERSIONS)
    if url.endswith("Xerath.json"):
        return FakeResponse(XERATH_DATA)
    return FakeResponse({}, ok=False, status_code=404)


def test_resolve_version_matches_major_minor(tmp_path, monkeypatch):
    monkeypatch.setattr(ddragon.requests, "get", _fake_get)
    version = ddragon.resolve_version("16.2.740.1491", cache_dir=tmp_path)
    assert version == "16.2.1"


def test_resolve_version_no_match_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ddragon.requests, "get", _fake_get)
    with pytest.raises(ddragon.DDragonError):
        ddragon.resolve_version("99.9.1.1", cache_dir=tmp_path)


def test_get_ability_cooldowns_returns_slots_in_order(tmp_path, monkeypatch):
    monkeypatch.setattr(ddragon.requests, "get", _fake_get)
    cooldowns = ddragon.get_ability_cooldowns("Xerath", "16.2.1", cache_dir=tmp_path)
    assert cooldowns[3] == [130, 115, 100]
    assert cooldowns[0] == [9, 8, 7, 6, 5]


def test_unknown_champion_raises(tmp_path, monkeypatch):
    monkeypatch.setattr(ddragon.requests, "get", _fake_get)
    with pytest.raises(ddragon.DDragonError):
        ddragon.get_ability_cooldowns("NotAChampion", "16.2.1", cache_dir=tmp_path)


def test_responses_are_cached_to_disk(tmp_path, monkeypatch):
    calls = []

    def counting_get(url, timeout=10):
        calls.append(url)
        return _fake_get(url, timeout)

    monkeypatch.setattr(ddragon.requests, "get", counting_get)
    ddragon.resolve_version("16.2.1.1", cache_dir=tmp_path)
    ddragon.resolve_version("16.2.1.1", cache_dir=tmp_path)
    assert calls.count("https://ddragon.leagueoflegends.com/api/versions.json") == 1

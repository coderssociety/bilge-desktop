import json

from bilge.brain.action_log import ActionLog


def test_dictated_and_copied_text_is_not_written_to_the_log(tmp_path):
    log = ActionLog(tmp_path / "actions.jsonl")
    log.record("typeText", {"text": "şifrem 1234"}, "ran", "Yazdım.")
    log.record("setVolume", {"action": "set", "level": 30}, "ran", "Ses seviyesi yüzde 30.")
    first, second = (json.loads(line) for line in (tmp_path / "actions.jsonl").read_text().splitlines())
    assert first["arguments"] == {"text": "<11 characters>"}
    assert second["arguments"] == {"action": "set", "level": "30"}

import json

import pytest
from journal import Journal


def test_restart_retries_identical_pending_tick(tmp_path):
    path = tmp_path / "producer.sqlite"
    journal = Journal(path, ["FAKE", "FAKE2"])
    original = journal.prepare("FAKE", 1000, .2)
    journal.close()  # broker may have received this, but acknowledgement was lost
    journal = Journal(path, ["FAKE", "FAKE2"])
    assert journal.prepare("FAKE2", 2000, 1) == original
    journal.acknowledge(original)
    following = journal.prepare("FAKE", 2001, .2)
    assert following["sequence"] == 2
    assert following["stream_id"] == original["stream_id"]
    assert following["event_id"] != original["event_id"]
    journal.close()


def test_symbols_sequence_independently_and_ack_is_checked(tmp_path):
    journal = Journal(tmp_path / "producer.sqlite", ["FAKE", "FAKE2"])
    first = journal.prepare("FAKE", 1000, .1)
    with pytest.raises(ValueError, match="does not match"):
        journal.acknowledge(first | {"price": 999})
    assert journal.prepare("FAKE", 1001, .1) == first
    journal.acknowledge(first)
    second = journal.prepare("FAKE2", 1001, .2)
    assert second["sequence"] == 1
    assert second["event_id"] == f'{second["stream_id"]}:FAKE2:1'
    journal.close()


def test_fixture_matches_versioned_schema():
    from conftest import ROOT
    import jsonschema
    schema = json.loads((ROOT / "contracts/tick-v1.schema.json").read_text())
    for line in (ROOT / "fixtures/replay-v1.jsonl").read_text().splitlines():
        row = json.loads(line)
        try:
            tick = json.loads(row["payload"])
        except ValueError:
            continue
        if tick is not None:
            jsonschema.validate(tick, schema)

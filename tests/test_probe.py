import io
import json

import pytest

from conftest import load


@pytest.fixture(scope="module")
def probe():
    return load("probe", "services/reliability-probe/probe.py")


@pytest.mark.parametrize("timestamp,expected", [(990, False), (991, True), (1002, True), (1003, False)])
def test_probe_validates_source_freshness(probe, monkeypatch, timestamp, expected):
    payload = {"timestamp": timestamp, "lastSymbol": "FAKE", "processedTicks": 1}
    monkeypatch.setattr(probe.time, "time", lambda: 1000)
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()))
    assert probe.check("http://test/strategy") is expected


def test_probe_rejects_other_symbol_sequence_failure(probe, monkeypatch):
    payload = {"timestamp": 999, "lastSymbol": "FAKE", "processedTicks": 1, "allSymbolsFresh": False}
    monkeypatch.setattr(probe.time, "time", lambda: 1000)
    monkeypatch.setattr(probe.urllib.request, "urlopen", lambda *args, **kwargs: io.BytesIO(json.dumps(payload).encode()))
    assert probe.check("http://test/strategy") is False

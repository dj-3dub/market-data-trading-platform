import json

import pytest

from conftest import load


@pytest.mark.parametrize("fail_during_pause", [False, True])
def test_fault_restores_service_and_keeps_evidence(monkeypatch, tmp_path, fail_during_pause):
    runner = load("failure_runner", "scripts/failure-suite.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    actions = []
    checks = 0

    def compose(*args):
        actions.append(args)
        if fail_during_pause and args[0] == "pause":
            raise TimeoutError("injection interrupted")

    def eventually(check, timeout):
        nonlocal checks
        checks += 1
        if checks > 1:
            raise TimeoutError("expected alert never fired")

    monkeypatch.setattr(runner, "compose", compose)
    monkeypatch.setattr(runner, "eventually", eventually)
    with pytest.raises(TimeoutError):
        runner.run("consumer")
    assert actions == [("pause", "strategy-engine"), ("unpause", "strategy-engine")]
    evidence = json.loads((tmp_path / "artifacts/fault-consumer.json").read_text())
    assert evidence["passed"] is False
    assert evidence["error"]

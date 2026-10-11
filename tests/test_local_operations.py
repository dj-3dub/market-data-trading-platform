"""Guard secret handling, stateful deployment and experiment provenance."""
import json
import stat

import pytest
import yaml

from conftest import ROOT, load
from evidence import new_report, save_report, source_digest, compose_workload
from local_config import grafana_password


def test_setup_preserves_configuration_and_password(monkeypatch, tmp_path):
    setup = load("setup_local", "scripts/setup-local.py")
    monkeypatch.delenv("GRAFANA_ADMIN_PASSWORD", raising=False)
    path = tmp_path / ".env"
    path.write_text("WEB_PORT=8090")
    setup.setup(tmp_path)
    first = path.read_text()
    password = grafana_password(tmp_path)
    assert len(password) >= 40
    assert "WEB_PORT=8090\n" in first
    assert stat.S_IMODE(path.stat().st_mode) == 0o600
    setup.setup(tmp_path)
    assert path.read_text() == first
    assert grafana_password(tmp_path) == password


def test_setup_respects_external_secret_and_refuses_symlink(monkeypatch, tmp_path):
    setup = load("setup_local", "scripts/setup-local.py")
    monkeypatch.setenv("GRAFANA_ADMIN_PASSWORD", "externally-managed-password")
    setup.setup(tmp_path)
    assert not (tmp_path / ".env").exists()
    assert grafana_password(tmp_path) == "externally-managed-password"
    monkeypatch.delenv("GRAFANA_ADMIN_PASSWORD")
    target = tmp_path / "private"
    target.write_text("keep me")
    (tmp_path / ".env").symlink_to(target)
    with pytest.raises(ValueError, match="symlink"):
        setup.setup(tmp_path)
    assert target.read_text() == "keep me"


def test_missing_password_fails_closed(monkeypatch, tmp_path):
    monkeypatch.delenv("GRAFANA_ADMIN_PASSWORD", raising=False)
    with pytest.raises(ValueError, match="make setup"):
        grafana_password(tmp_path)


def test_compose_storage_access_and_internal_kafka_contract():
    config = yaml.safe_load((ROOT / "docker-compose.yml").read_text())
    services = config["services"]
    for name, service in services.items():
        assert service["restart"] == "unless-stopped", name
        assert all(port.startswith("127.0.0.1:") for port in service.get("ports", [])), name
    expected = {
        "kafka": {"kafka-data:/var/lib/kafka/data"},
        "market-data": {"producer-state:/data"},
        "strategy-engine": {"strategy-state:/data"},
        "zookeeper": {"zookeeper-data:/var/lib/zookeeper/data", "zookeeper-log:/var/lib/zookeeper/log"},
        "grafana": {"grafana-data:/var/lib/grafana"},
        "prometheus": {"prometheus-data:/prometheus"},
    }
    for name, volumes in expected.items():
        assert volumes <= set(services[name]["volumes"])
        assert all(volume.split(":")[0] in config["volumes"] for volume in volumes)
    kafka = services["kafka"]
    assert kafka["ports"] == ["127.0.0.1:${KAFKA_PORT:-9092}:29092"]
    assert "INTERNAL://kafka:9092" in kafka["environment"]["KAFKA_ADVERTISED_LISTENERS"]
    assert "HOST://localhost:${KAFKA_PORT:-9092}" in kafka["environment"]["KAFKA_ADVERTISED_LISTENERS"]
    assert kafka["environment"]["KAFKA_INTER_BROKER_LISTENER_NAME"] == "INTERNAL"
    password = next(value for value in services["grafana"]["environment"] if value.startswith("GF_SECURITY_ADMIN_PASSWORD="))
    assert "${GRAFANA_ADMIN_PASSWORD:?" in password
    assert config["networks"]["trading-net"] == {"driver": "bridge"}
    assert all(value is None for value in config["volumes"].values())


def test_evidence_is_traceable_and_preserves_each_run(monkeypatch, tmp_path):
    import evidence
    monkeypatch.setattr(evidence, "command", lambda *args: None)
    (tmp_path / "source.py").write_text("print('one')\n")
    (tmp_path / ".env").write_text("GRAFANA_ADMIN_PASSWORD=private\n")
    first_digest = source_digest(tmp_path)
    (tmp_path / ".env").write_text("GRAFANA_ADMIN_PASSWORD=changed-private\n")
    assert source_digest(tmp_path) == first_digest
    first = new_report(tmp_path, "consumer", {"poll_interval_seconds": 2})
    first_file = save_report(tmp_path, first, "fault-consumer")
    first_bytes = first_file.read_bytes()
    assert source_digest(tmp_path) == first_digest
    second = new_report(tmp_path, "consumer", {})
    second_file = save_report(tmp_path, second, "fault-consumer")
    assert first_file != second_file
    assert first_file.read_bytes() == first_bytes
    assert json.loads((tmp_path / "artifacts/fault-consumer.json").read_text())["run_id"] == second["run_id"]
    assert first["source"]["git_commit"] is None
    assert first["started_at_utc"] <= first["finished_at_utc"]
    assert "changed-private" not in first_file.read_text()
    (tmp_path / "source.py").write_text("print('two')\n")
    assert source_digest(tmp_path) != first_digest


def test_workload_report_excludes_environment_secrets(monkeypatch, tmp_path):
    import evidence
    config = {"services": {
        "market-data": {"environment": {"TICK_INTERVAL_SECONDS": "0.25", "KAFKA_TICKS_TOPIC": "ticks"}},
        "grafana": {"environment": {"GF_SECURITY_ADMIN_PASSWORD": "do-not-record-this"}},
    }}
    monkeypatch.setattr(evidence, "command", lambda *args: json.dumps(config))
    workload = compose_workload(tmp_path)
    assert workload["tick_interval_seconds"] == 0.25
    assert "do-not-record-this" not in json.dumps(workload)


def test_persistence_failure_restores_workload_and_records_failure(monkeypatch, tmp_path):
    runner = load("persistence_failure", "scripts/verify-persistence.py")
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "new_report", lambda *args: {"run_id": "a" * 32, "passed": False})
    monkeypatch.setattr(runner, "compose_workload", lambda *args: {})
    monkeypatch.setattr(runner, "historical_sample", lambda *args: [{"value": [1, "1"]}])
    monkeypatch.setattr(runner, "offsets", lambda: {"ticks:0": 10})
    monkeypatch.setattr(runner, "eventually", lambda check, **kwargs: check())
    monkeypatch.setattr(runner, "http", lambda *args, **kwargs: {"status": "ready", "database": "ok"})
    monkeypatch.setattr(runner, "kafka", lambda *args, **kwargs: "ok")
    actions = []

    def compose(*args, **kwargs):
        actions.append(args)
        if "--force-recreate" in args:
            raise RuntimeError("injected recreation failure")
        return ""

    monkeypatch.setattr(runner, "compose", compose)
    with pytest.raises(RuntimeError, match="recreation failure"):
        runner.main()
    assert ("start", "market-data", "strategy-engine") in actions
    report = json.loads((tmp_path / "artifacts/persistence.json").read_text())
    assert report["passed"] is False
    assert "recreation failure" in report["error"]


@pytest.mark.parametrize("offsets_survive", [True, False])
def test_persistence_requires_records_offsets_dashboard_and_history(monkeypatch, tmp_path, offsets_survive):
    runner = load("persistence_checks", "scripts/verify-persistence.py")
    run_id = "b" * 32
    uid = "persistence-" + run_id[:12]
    monkeypatch.setattr(runner, "ROOT", tmp_path)
    monkeypatch.setattr(runner, "new_report", lambda *args: {"run_id": run_id, "passed": False})
    monkeypatch.setattr(runner, "compose_workload", lambda *args: {})
    monkeypatch.setattr(runner, "compose", lambda *args, **kwargs: "")
    monkeypatch.setattr(runner, "eventually", lambda check, **kwargs: check())
    monkeypatch.setattr(runner, "historical_sample", lambda *args: [{"value": [1, "1"]}])
    offset_states = iter([{"ticks:0": 10}, {"ticks:0": 10 if offsets_survive else 0}])
    monkeypatch.setattr(runner, "offsets", lambda: next(offset_states))
    monkeypatch.setattr(runner, "kafka", lambda tool, *args, **kwargs:
                        run_id if tool == "kafka-console-consumer" else "ok")
    requests = []
    timestamps = iter([100, 101])

    def http(url, *args, **kwargs):
        requests.append((url, kwargs.get("method")))
        if url.endswith("/strategy"):
            return {"timestamp": next(timestamps)}
        if "/api/dashboards/uid/" in url:
            return {"dashboard": {"uid": uid}}
        return {"status": "ready", "database": "ok"}

    monkeypatch.setattr(runner, "http", http)
    if offsets_survive:
        runner.main()
    else:
        with pytest.raises(RuntimeError, match="offsets changed"):
            runner.main()
    report = json.loads((tmp_path / "artifacts/persistence.json").read_text())
    assert report["passed"] is offsets_survive
    assert any(method == "DELETE" for _, method in requests)
    if offsets_survive:
        assert all(report["checks"].values())

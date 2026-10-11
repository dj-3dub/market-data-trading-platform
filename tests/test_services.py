from unittest.mock import MagicMock

import httpx
import pytest
from fastapi.testclient import TestClient


@pytest.mark.parametrize("path", ["/price", "/strategy"])
@pytest.mark.parametrize("fault", ["timeout", "invalid-json", "unavailable"])
def test_gateway_dependency_failures(gateway, monkeypatch, path, fault):
    def upstream(request):
        if fault == "timeout":
            raise httpx.ReadTimeout("injected", request=request)
        if fault == "invalid-json":
            return httpx.Response(200, text="not json")
        return httpx.Response(503, json={"error": "unavailable"})

    real_client = httpx.AsyncClient
    monkeypatch.setattr(gateway.httpx, "AsyncClient", lambda **kwargs: real_client(
        transport=httpx.MockTransport(upstream), **kwargs))
    metric = gateway.REQUEST_COUNT.labels(endpoint=path, method="GET", status="503")
    before = metric._value.get()
    response = TestClient(gateway.app).get(path)
    assert response.status_code == 503
    assert metric._value.get() == before + 1


@pytest.mark.parametrize("close_fails", [False, True])
def test_failed_publish_does_not_advance_state(market, monkeypatch, close_fails, tmp_path):
    from journal import Journal
    monkeypatch.setattr(market, "open_journal", lambda: Journal(tmp_path / "producer.sqlite", market.symbols))
    producer = MagicMock()
    if close_fails:
        producer.close.side_effect = TimeoutError("cleanup timed out")
    producer.send.return_value.get.side_effect = TimeoutError("no acknowledgment")
    monkeypatch.setattr(market, "KafkaProducer", lambda **kwargs: producer)
    monkeypatch.setattr(market, "latest", {})
    monkeypatch.setattr(market, "last_published", {})
    stop = MagicMock()
    stop.is_set.side_effect = [False, True]
    monkeypatch.setattr(market, "stop", stop)
    market.publish_loop()
    assert market.latest == {}
    assert market.last_published == {}
    assert market.ready().status_code == 503
    producer.close.assert_called_once_with(timeout=0)


def test_market_symbol_and_staleness(market, monkeypatch):
    assert market.get_price_tick("OTHER").status_code == 404
    monkeypatch.setattr(market, "latest", {"FAKE": {"symbol": "FAKE", "timestamp": 1}})
    monkeypatch.setattr(market, "last_published", {})
    assert market.ready().status_code == 503

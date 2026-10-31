from __future__ import annotations

import json
from pathlib import Path

import httpx
import pytest

from epic_free_games_tracker.client import EpicStoreClient, save_debug_response


def _transport(
    payload: dict[str, object], *, statuses: list[int] | None = None
) -> tuple[httpx.MockTransport, dict[str, int]]:
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        status = (statuses or [200])[min(calls["n"] - 1, len(statuses or [200]) - 1)]
        return httpx.Response(status, json=payload, request=request)

    return httpx.MockTransport(handler), calls


def test_get_games_sends_locale_country(
    sample_payload: dict[str, object],
) -> None:
    seen: dict[str, str] = {}

    def handler(request: httpx.Request) -> httpx.Response:
        seen.update(dict(request.url.params))
        return httpx.Response(200, json=sample_payload, request=request)

    with EpicStoreClient(transport=httpx.MockTransport(handler)) as client:
        games = client.get_games(locale="en-GB", country="GB")
    assert seen == {"locale": "en-GB", "country": "GB", "allowCountries": "GB"}
    assert len(games) == 3


def test_retries_transient_5xx_then_succeeds(
    sample_payload: dict[str, object],
) -> None:
    transport, calls = _transport(sample_payload, statuses=[503, 500, 200])
    with EpicStoreClient(transport=transport, sleep=lambda _: None) as client:
        games = client.get_games()
    assert len(games) == 3
    assert calls["n"] == 3


def test_persistent_failure_raises_after_three_attempts(
    sample_payload: dict[str, object],
) -> None:
    transport, calls = _transport(sample_payload, statuses=[503])
    with (
        EpicStoreClient(transport=transport, sleep=lambda _: None) as client,
        pytest.raises(httpx.HTTPError),
    ):
        client.get_games()
    assert calls["n"] == 3


def test_retries_429_and_honours_retry_after(
    sample_payload: dict[str, object],
) -> None:
    sleeps: list[float] = []
    calls = {"n": 0}

    def handler(request: httpx.Request) -> httpx.Response:
        calls["n"] += 1
        if calls["n"] == 1:
            return httpx.Response(
                429, headers={"Retry-After": "2"}, json={}, request=request
            )
        return httpx.Response(200, json=sample_payload, request=request)

    with EpicStoreClient(
        transport=httpx.MockTransport(handler), sleep=sleeps.append
    ) as client:
        assert len(client.get_games()) == 3
    assert calls["n"] == 2
    assert sleeps == [2.0]


def test_debug_save_writes_payload(
    sample_payload: dict[str, object], tmp_path: Path
) -> None:
    transport, _ = _transport(sample_payload)
    with EpicStoreClient(transport=transport) as client:
        client.get_games(debug_dir=tmp_path)
    files = list(tmp_path.glob("epic_response_*.json"))
    assert len(files) == 1
    assert json.loads(files[0].read_text(encoding="utf-8")) == sample_payload


def test_construction_survives_malformed_no_proxy(
    sample_payload: dict[str, object], monkeypatch: pytest.MonkeyPatch
) -> None:
    # httpx's trust_env parsing crashes on NO_PROXY values such as
    # "[::1]"; the client resolves proxies explicitly instead.
    monkeypatch.setenv("NO_PROXY", "[::1],localhost")
    monkeypatch.setenv("HTTPS_PROXY", "http://proxy.example:3128")
    transport, _ = _transport(sample_payload)
    with EpicStoreClient(transport=transport) as client:
        assert len(client.get_games()) == 3


def test_save_debug_response_returns_path(tmp_path: Path) -> None:
    path = save_debug_response({"data": {}}, tmp_path)
    assert path.exists()
    assert path.suffix == ".json"


def test_non_dict_catalog_is_validation_error_not_attribute_error(
    sample_payload: dict[str, object],
) -> None:
    payload = {**sample_payload, "data": {"Catalog": ["not", "a", "dict"]}}
    transport, _ = _transport(payload)
    with EpicStoreClient(transport=transport) as client, pytest.raises(ValueError):
        client.get_games()

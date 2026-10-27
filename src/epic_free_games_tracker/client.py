"""HTTP client for the Epic free-games promotions feed.

One client, with retries on transient 5xx responses and a single place
for headers, timeouts, and debug capture. The original project had three
clients (one httpx, two requests) with different retry behaviour; this
replaces all three. The client is a context manager: closing it is the
caller's job, and :func:`fetch_games` owns that when it creates one.
"""

from __future__ import annotations

import json
import os
import time
from datetime import datetime
from pathlib import Path
from typing import TYPE_CHECKING, Any

import httpx

from .models import EpicResponse, Game

if TYPE_CHECKING:
    from collections.abc import Mapping

BASE_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
_RETRYABLE_STATUS = frozenset({500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_TIMEOUT = 30.0


def _proxy_kwargs(*, transport: httpx.BaseTransport | None) -> dict[str, Any]:
    """Proxy/CA settings resolved explicitly, without env parsing.

    httpx's ``trust_env`` parsing crashes on some ``NO_PROXY`` values
    (IPv6 entries such as ``[::1]``), so this client never relies on
    it: it reads the proxy URL and CA bundle from the environment
    itself and passes them explicitly. With a custom transport
    (tests), no proxy is passed at all, so the transport is not
    shadowed by proxy mounts. Without a proxy in the environment,
    requests go direct, as they would by default.
    """
    kwargs: dict[str, Any] = {"trust_env": False}
    if transport is not None:
        return kwargs
    proxy_url = (
        os.environ.get("HTTPS_PROXY")
        or os.environ.get("https_proxy")
        or os.environ.get("HTTP_PROXY")
        or os.environ.get("http_proxy")
    )
    if proxy_url:
        kwargs["proxy"] = proxy_url
    for ca_var in ("SSL_CERT_FILE", "REQUESTS_CA_BUNDLE", "CURL_CA_BUNDLE"):
        ca_path = os.environ.get(ca_var)
        if ca_path and Path(ca_path).is_file():
            kwargs["verify"] = ca_path
            break
    return kwargs


class EpicStoreClient:
    """Fetches games from the promotions feed."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = _TIMEOUT,
    ) -> None:
        self.base_url = BASE_URL
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={
                "User-Agent": (
                    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
                ),
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            **_proxy_kwargs(transport=transport),
        )

    def __enter__(self) -> EpicStoreClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()

    def close(self) -> None:
        self._client.close()

    def get_games(
        self,
        *,
        locale: str = "en-US",
        country: str = "US",
        debug_dir: Path | None = None,
    ) -> list[Game]:
        """Fetch and validate every element in the feed.

        Retries transient 5xx responses and transport errors up to
        three attempts with backoff. Raises :class:`httpx.HTTPError`
        when every attempt fails, so callers can report it once.
        """
        params: Mapping[str, str] = {
            "locale": locale,
            "country": country,
            "allowCountries": country,
        }
        last_error: httpx.HTTPError | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.get(self.base_url, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                else:
                    response.raise_for_status()
                    payload: dict[str, Any] = response.json()
                    if debug_dir is not None:
                        save_debug_response(payload, debug_dir)
                    return EpicResponse.model_validate(payload).get_games()
            if attempt < _MAX_ATTEMPTS - 1:
                time.sleep(0.5 * (2**attempt))
        assert last_error is not None  # loop always sets it on failure
        raise last_error


def save_debug_response(payload: dict[str, Any], debug_dir: Path) -> Path:
    """Save a raw feed payload under ``debug_dir``; returns its path."""
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    debug_file = debug_dir / f"epic_response_{timestamp}.json"
    debug_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return debug_file


def load_games_from_file(path: Path) -> list[Game]:
    """Load games from a saved feed payload (offline / demo use)."""
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return EpicResponse.model_validate(payload).get_games()

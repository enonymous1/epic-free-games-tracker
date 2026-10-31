"""HTTP client for the Epic free-games promotions feed.

One client, with retries on transient responses and a single place
for headers, timeouts, and debug capture. The original project had three
clients (one httpx, two requests) with different retry behaviour; this
replaces all three. The client is a context manager: closing it is the
caller's job, and :func:`EpicStoreClient.get_games` callers own that
when they create one (the CLI uses ``with``).
"""

from __future__ import annotations

import json
import os
import random
import time
from collections.abc import Callable, Mapping
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

from . import __version__
from .models import EpicResponse, Game

BASE_URL = "https://store-site-backend-static.ak.epicgames.com/freeGamesPromotions"
_RETRYABLE_STATUS = frozenset({429, 500, 502, 503, 504})
_MAX_ATTEMPTS = 3
_TIMEOUT = 30.0


def _proxy_kwargs(*, transport: httpx.BaseTransport | None) -> dict[str, Any]:
    """Proxy/CA settings resolved explicitly, without env parsing.

    httpx's ``trust_env`` parsing crashes on some ``NO_PROXY`` values
    (IPv6 entries such as ``[::1]`` raise
    ``InvalidURL: Invalid port: ':1]'`` at client construction), so
    this client never relies on it: it reads the proxy URL and CA
    bundle from the environment itself and passes them explicitly.
    With a custom transport (tests), no proxy is passed at all, so
    the transport is not shadowed by proxy mounts. Without a proxy
    in the environment, requests go direct, as they would by
    default. Known limitation: ``NO_PROXY`` is not honoured here —
    when a proxy is set, it is used for the feed host too.
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


def _retry_delay(response: httpx.Response | None, attempt: int) -> float:
    """Backoff for the next attempt, honouring ``Retry-After``.

    A 429 with a ``Retry-After`` header wins over exponential
    backoff; otherwise the delay is ``0.5 * 2**attempt`` plus a
    small jitter, so concurrent clients do not retry in lockstep.
    """
    if response is not None:
        retry_after = response.headers.get("Retry-After")
        if retry_after:
            try:
                return float(retry_after)
            except ValueError:
                pass
    return float(0.5 * (2**attempt) + random.uniform(0, 0.25))  # noqa: S311


class EpicStoreClient:
    """Fetches games from the promotions feed."""

    def __init__(
        self,
        *,
        transport: httpx.BaseTransport | None = None,
        timeout: float = _TIMEOUT,
        base_url: str = BASE_URL,
        sleep: Callable[[float], None] = time.sleep,
    ) -> None:
        """Create a client.

        ``base_url`` is a parameter (not just the module constant)
        so staging or a local mock feed can be pointed at without
        editing code. ``sleep`` is injectable so retry timing is a
        unit test, not a wall clock.
        """
        self.base_url = base_url
        self._sleep = sleep
        self._client = httpx.Client(
            transport=transport,
            timeout=timeout,
            headers={
                "User-Agent": (
                    f"epic-free-games-tracker/{__version__} "
                    "(+https://github.com/enonymous1/epic-free-games-tracker)"
                ),
                "Accept": "application/json",
                "Accept-Language": "en-US,en;q=0.9",
            },
            follow_redirects=True,
            **_proxy_kwargs(transport=transport),
        )

    def __enter__(self) -> EpicStoreClient:
        """Return self for use as a context manager."""
        return self

    def __exit__(self, *exc: object) -> None:
        """Close the underlying client; do not suppress exceptions."""
        self.close()

    def close(self) -> None:
        """Close the underlying httpx client and release connections."""
        self._client.close()

    def get_games(
        self,
        *,
        locale: str = "en-US",
        country: str = "US",
        debug_dir: Path | None = None,
    ) -> list[Game]:
        """Fetch and validate every element in the feed.

        Retries transient responses (429 and 5xx) and transport
        errors up to three attempts with backoff. Raises
        :class:`httpx.HTTPError` when every attempt fails, so
        callers can report it once. A validation failure is *not*
        retried: a malformed payload will not become valid by
        asking again, and it surfaces as a ``ValidationError``
        (a ``ValueError``) for the CLI to report.
        """
        params: Mapping[str, str] = {
            "locale": locale,
            "country": country,
            "allowCountries": country,
        }
        last_error: httpx.HTTPError | None = None
        last_response: httpx.Response | None = None
        for attempt in range(_MAX_ATTEMPTS):
            try:
                response = self._client.get(self.base_url, params=params)
            except httpx.HTTPError as exc:
                last_error = exc
                last_response = None
            else:
                if response.status_code in _RETRYABLE_STATUS:
                    last_error = httpx.HTTPStatusError(
                        f"HTTP {response.status_code}",
                        request=response.request,
                        response=response,
                    )
                    last_response = response
                else:
                    response.raise_for_status()
                    payload: dict[str, Any] = response.json()
                    if debug_dir is not None:
                        save_debug_response(payload, debug_dir)
                    return EpicResponse.model_validate(payload).get_games()
            if attempt < _MAX_ATTEMPTS - 1:
                self._sleep(_retry_delay(last_response, attempt))
        if last_error is None:  # pragma: no cover - loop always sets it
            raise RuntimeError("retry loop ended without an error")
        raise last_error


def save_debug_response(payload: dict[str, Any], debug_dir: Path) -> Path:
    """Save a raw feed payload under ``debug_dir``; returns its path.

    The filename uses a UTC timestamp to the second. Two saves in
    the same second overwrite each other; debug saves are rare
    enough that this is accepted, and the CLI saves at most once
    per run.
    """
    debug_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
    debug_file = debug_dir / f"epic_response_{timestamp}.json"
    debug_file.write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return debug_file


def load_games_from_file(path: Path) -> list[Game]:
    """Load games from a saved feed payload (offline / demo use).

    Raises ``OSError`` for a missing/unreadable file and
    ``ValueError`` (including Pydantic ``ValidationError``) for a
    malformed payload, matching the CLI's error handling.
    """
    payload: dict[str, Any] = json.loads(path.read_text(encoding="utf-8"))
    return EpicResponse.model_validate(payload).get_games()

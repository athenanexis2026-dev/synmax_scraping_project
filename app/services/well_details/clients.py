"""Firecrawl clients used to fetch official NM OCD Well Details content."""

from __future__ import annotations

import json
import shlex
import urllib.error
import urllib.request
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from app.services.well_details.errors import FirecrawlBrowserError
from app.services.well_details.parser import (
    text_from_browser_execute_response,
    well_details_snapshot_to_html,
)


# ============================================================================
# CONFIGURATION CONSTANTS
# ============================================================================
FIRECRAWL_API_BASE_URL = "https://api.firecrawl.dev/v2"
OpenRequest = Callable[[urllib.request.Request, float], bytes]


# ============================================================================
# FIRECRAWL CLIENTS
# ============================================================================
@dataclass
class FirecrawlBrowserClient:
    """Client for Firecrawl browser sessions used to verify/save a profile."""

    api_key: str
    base_url: str = FIRECRAWL_API_BASE_URL
    timeout: float = 90.0
    opener: OpenRequest | None = None

    def create_session(
        self,
        *,
        profile_name: str,
        ttl_seconds: int = 900,
        activity_ttl_seconds: int = 900,
    ) -> dict[str, Any]:
        """Create a persistent browser session and return Firecrawl's session data."""

        payload = {
            "ttl": ttl_seconds,
            "activityTtl": activity_ttl_seconds,
            "streamWebView": True,
            "profile": {"name": profile_name, "saveChanges": True},
        }
        return self._request_json("POST", "/browser", payload)

    def execute_node(self, session_id: str, code: str) -> dict[str, Any]:
        """Run Node/Playwright code in a browser session."""

        return self._request_json(
            "POST",
            f"/browser/{session_id}/execute",
            {"code": code, "language": "node"},
        )

    def execute_bash(self, session_id: str, code: str) -> dict[str, Any]:
        """Run a bash command in a browser session."""

        return self._request_json(
            "POST",
            f"/browser/{session_id}/execute",
            {"code": code, "language": "bash"},
        )

    def close_session(self, session_id: str) -> dict[str, Any]:
        """Close a browser session so profile changes are saved."""

        return self._request_json("DELETE", f"/browser/{session_id}", None)

    def _request_json(
        self,
        method: str,
        path: str,
        payload: dict[str, Any] | None,
    ) -> dict[str, Any]:
        data = json.dumps(payload).encode("utf-8") if payload is not None else None
        request = urllib.request.Request(
            self.base_url.rstrip("/") + path,
            data=data,
            method=method,
            headers={
                "Authorization": f"Bearer {self.api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
        )
        try:
            raw_response = self._open(request)
            response = json.loads(raw_response.decode("utf-8"))
        except (TimeoutError, urllib.error.URLError, json.JSONDecodeError) as error:
            raise FirecrawlBrowserError(
                f"Firecrawl browser operation failed: {error}"
            ) from error

        if not response.get("success"):
            error = response.get("error") or response.get("message") or response
            raise FirecrawlBrowserError(f"Firecrawl browser operation failed: {error}")
        return response

    def _open(self, request: urllib.request.Request) -> bytes:
        if self.opener is not None:
            return self.opener(request, self.timeout)

        with urllib.request.urlopen(request, timeout=self.timeout) as response:
            return response.read()


@dataclass
class FirecrawlBrowserSessionWellDetailsClient:
    """Fetch Well Details HTML through an already-open Firecrawl browser session."""

    browser_client: FirecrawlBrowserClient
    session_id: str
    wait_for_ms: int = 5000

    def scrape_html(self, url: str) -> str:
        """Navigate the live browser session and return the resulting page HTML."""

        response = self.browser_client.execute_bash(
            self.session_id,
            (
                f"agent-browser open {shlex.quote(url)} && "
                f"sleep {max(0, self.wait_for_ms / 1000):g} && "
                "agent-browser snapshot"
            ),
        )
        snapshot = text_from_browser_execute_response(response)
        if snapshot is None:
            raise FirecrawlBrowserError("Browser session returned no page snapshot")
        return well_details_snapshot_to_html(snapshot)

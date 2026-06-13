"""HTTP cache response helpers."""

from __future__ import annotations

import hashlib
import json
from typing import Any

from fastapi import Request
from fastapi.responses import JSONResponse, Response


# ============================================================================
# HTTP CACHE SETTINGS
# ============================================================================
CACHE_CONTROL = "public, max-age=300"


# ============================================================================
# HTTP CACHE RESPONSES
# ============================================================================
def json_cache_response(content: Any, request: Request) -> Response:
    """Return a JSON response with Cache-Control and ETag handling."""

    etag = build_etag(content)
    headers = {"Cache-Control": CACHE_CONTROL, "ETag": etag}
    if etag_matches(request.headers.get("if-none-match"), etag):
        return Response(status_code=304, headers=headers)
    return JSONResponse(content=content, headers=headers)


def build_etag(content: Any) -> str:
    """Build a stable ETag hash from response content."""

    payload = json.dumps(
        content, sort_keys=True, separators=(",", ":"), default=str
    ).encode()
    digest = hashlib.sha256(payload).hexdigest()
    return f'"{digest}"'


def etag_matches(header_value: str | None, etag: str) -> bool:
    """Return whether an If-None-Match header contains the current ETag."""

    if not header_value:
        return False
    return any(candidate.strip() == etag for candidate in header_value.split(","))

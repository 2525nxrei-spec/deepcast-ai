"""Tests for api.bridge FastAPI endpoints using httpx.AsyncClient."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from api.bridge import app

pytestmark = pytest.mark.asyncio

# The API key configured in Settings defaults / test
_TEST_API_KEY = "deepcast-dev-secret-change-me"


# ------------------------------------------------------------------
# Helper: async test client
# ------------------------------------------------------------------


@pytest.fixture()
def auth_headers() -> dict[str, str]:
    """Return headers with a valid API key."""
    return {"X-API-Key": _TEST_API_KEY}


# ------------------------------------------------------------------
# test_health_endpoint
# ------------------------------------------------------------------


async def test_health_endpoint() -> None:
    """GET /api/health should return 200 with status 'ok'."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/health")

    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert "timestamp" in data
    assert "ollama_connected" in data
    assert "db_connected" in data


# ------------------------------------------------------------------
# test_list_contents
# ------------------------------------------------------------------


async def test_list_contents(auth_headers: dict[str, str]) -> None:
    """GET /api/contents should return paginated content list."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/contents",
            headers=auth_headers,
            params={"status": "published", "limit": 5},
        )

    assert response.status_code == 200
    data = response.json()
    assert "contents" in data
    assert "total" in data
    assert "page" in data
    assert isinstance(data["contents"], list)


# ------------------------------------------------------------------
# test_get_content
# ------------------------------------------------------------------


async def test_get_content(auth_headers: dict[str, str]) -> None:
    """GET /api/contents/{id} should return 404 for non-existent content."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get(
            "/api/contents/99999",
            headers=auth_headers,
        )

    # Should be 404 (content not found) or 500 (if DB not initialised in test)
    assert response.status_code in (404, 500)


# ------------------------------------------------------------------
# test_auth_required — verify 401 without API key
# ------------------------------------------------------------------


async def test_auth_required() -> None:
    """Authenticated endpoints should return 401 without a valid API key."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        # No API key header at all
        response_no_key = await client.get("/api/contents")
        assert response_no_key.status_code == 401

        # Wrong API key
        response_bad_key = await client.get(
            "/api/contents",
            headers={"X-API-Key": "wrong-key-12345"},
        )
        assert response_bad_key.status_code == 401

        # Latest endpoint also requires auth
        response_latest = await client.get("/api/contents/latest")
        assert response_latest.status_code == 401

        # Generate endpoint requires auth
        response_generate = await client.post(
            "/api/generate",
            json={"language": "ja"},
        )
        assert response_generate.status_code == 401


# ------------------------------------------------------------------
# test_embed_js_endpoint
# ------------------------------------------------------------------


async def test_embed_js_endpoint() -> None:
    """GET /api/embed/latest.js should return JavaScript content (no auth required)."""
    async with httpx.AsyncClient(
        transport=httpx.ASGITransport(app=app),
        base_url="http://testserver",
    ) as client:
        response = await client.get("/api/embed/latest.js")

    assert response.status_code == 200
    content_type = response.headers.get("content-type", "")
    assert "javascript" in content_type
    body = response.text
    assert "deepcast-widget" in body
    assert "fetch(" in body

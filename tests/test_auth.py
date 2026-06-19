"""Tests basicos de autenticacion."""
from __future__ import annotations

import pytest
from httpx import ASGITransport, AsyncClient

from backend.app.main import app


@pytest.fixture
def client():
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


@pytest.mark.asyncio
async def test_health_endpoint(client):
    """El health endpoint debe responder 200."""
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_login_requires_credentials(client):
    """Login sin credenciales debe devolver 422."""
    response = await client.post("/api/v1/auth/login", json={})
    assert response.status_code == 422

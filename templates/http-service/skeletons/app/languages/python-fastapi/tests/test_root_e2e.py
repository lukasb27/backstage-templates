import pytest
from httpx import ASGITransport, AsyncClient

from app.main import app


@pytest.mark.e2e
async def test_root_returns_ok_over_http():
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        response = await client.get("/")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}

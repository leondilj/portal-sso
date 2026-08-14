import httpx
import pytest
import respx

from app.portal_client import PortalClient, TokenExchangeError


async def test_exchange_code_success() -> None:
    with respx.mock:
        respx.post("http://portal.test/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok", "refresh_token": "ref"})
        )
        client = PortalClient("http://portal.test/token", "segredo")
        result = await client.exchange_code("code-1")

    assert result.access_token == "tok"
    assert result.refresh_token == "ref"


async def test_exchange_code_sends_client_secret() -> None:
    with respx.mock:
        route = respx.post("http://portal.test/token").mock(
            return_value=httpx.Response(200, json={"access_token": "tok", "refresh_token": None})
        )
        client = PortalClient("http://portal.test/token", "segredo-certo")
        await client.exchange_code("code-1")

    sent = route.calls.last.request
    assert sent.content
    import json

    body = json.loads(sent.content)
    assert body == {"code": "code-1", "client_secret": "segredo-certo"}


async def test_exchange_code_maps_portal_error() -> None:
    with respx.mock:
        respx.post("http://portal.test/token").mock(
            return_value=httpx.Response(400, json={"error": "expired"})
        )
        client = PortalClient("http://portal.test/token", "segredo")
        with pytest.raises(TokenExchangeError) as exc_info:
            await client.exchange_code("code-1")

    assert exc_info.value.error == "expired"


async def test_exchange_code_network_error() -> None:
    with respx.mock:
        respx.post("http://portal.test/token").mock(side_effect=httpx.ConnectError("boom"))
        client = PortalClient("http://portal.test/token", "segredo")
        with pytest.raises(TokenExchangeError) as exc_info:
            await client.exchange_code("code-1")

    assert exc_info.value.error == "network_error"

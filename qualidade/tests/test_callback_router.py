from datetime import UTC, datetime, timedelta

import jwt as pyjwt
from cryptography.hazmat.primitives.asymmetric import ec

from app.portal_client import PortalToken, TokenExchangeError
from app.sessions import SESSION_COOKIE_NAME


def test_callback_success_sets_session_and_redirects(harness, sign_jwt) -> None:
    token = sign_jwt({"app_metadata": {"acessos": {"qualidade": ["gerente"]}}})

    async def fake_exchange(code: str) -> PortalToken:
        assert code == "code-abc"
        return PortalToken(access_token=token, refresh_token="ref-xyz")

    harness.app.state.portal_client.exchange_code = fake_exchange

    response = harness.client.get("/callback", params={"code": "code-abc"}, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    cookie_value = response.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_value is not None
    session = harness.app.state.session_manager.decode(cookie_value)
    assert session.email == "joao@lab.internal"
    assert session.papeis == ["gerente"]


def test_callback_portal_exchange_error_shows_message_no_cookie(harness) -> None:
    async def fake_exchange(code: str) -> PortalToken:
        raise TokenExchangeError("expired")

    harness.app.state.portal_client.exchange_code = fake_exchange

    response = harness.client.get("/callback", params={"code": "code-abc"}, follow_redirects=False)

    assert response.status_code == 400
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    assert "expirou" in response.text


def test_callback_invalid_jwt_from_portal_is_rejected(harness) -> None:
    """Defesa em profundidade: mesmo se o portal devolver 200, esta app
    valida a assinatura por conta propria e nao aceita um token forjado."""
    other_key = ec.generate_private_key(ec.SECP256R1())
    forged_token = pyjwt.encode(
        {
            "sub": "user-1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        other_key,
        algorithm="ES256",
    )

    async def fake_exchange(code: str) -> PortalToken:
        return PortalToken(access_token=forged_token, refresh_token=None)

    harness.app.state.portal_client.exchange_code = fake_exchange

    response = harness.client.get("/callback", params={"code": "code-abc"}, follow_redirects=False)

    assert response.status_code == 401
    assert response.cookies.get(SESSION_COOKIE_NAME) is None


def test_callback_no_papel_for_qualidade_denies_access(harness, sign_jwt) -> None:
    token = sign_jwt({"app_metadata": {"acessos": {"vendas": ["analista"]}}})

    async def fake_exchange(code: str) -> PortalToken:
        return PortalToken(access_token=token, refresh_token=None)

    harness.app.state.portal_client.exchange_code = fake_exchange

    response = harness.client.get("/callback", params={"code": "code-abc"}, follow_redirects=False)

    assert response.status_code == 403
    assert response.cookies.get(SESSION_COOKIE_NAME) is None

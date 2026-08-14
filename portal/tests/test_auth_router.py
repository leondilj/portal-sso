from app.sessions import SESSION_COOKIE_NAME
from app.supabase_client import InvalidCredentialsError, SupabaseSession


def test_login_success_sets_cookie_and_redirects(harness, sign_jwt) -> None:
    token = sign_jwt(
        {
            "sub": "user-1",
            "email": "joao@lab.internal",
            "app_metadata": {"acessos": {"qualidade": ["gerente"]}},
        }
    )

    async def fake_login(email: str, password: str) -> SupabaseSession:
        return SupabaseSession(
            user_id="user-1",
            email="joao@lab.internal",
            access_token=token,
            refresh_token="refresh-xyz",
        )

    harness.app.state.supabase_client.password_login = fake_login

    response = harness.client.post(
        "/login",
        data={"email": "joao@lab.internal", "password": "senha"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/"

    cookie_value = response.cookies.get(SESSION_COOKIE_NAME)
    assert cookie_value is not None

    decoded = harness.app.state.session_manager.decode(cookie_value)
    assert decoded.email == "joao@lab.internal"
    assert decoded.acessos == {"qualidade": ["gerente"]}
    assert decoded.access_token == token
    assert decoded.refresh_token == "refresh-xyz"


def test_login_failure_rerenders_with_error_and_no_cookie(harness) -> None:
    async def fake_login(email: str, password: str) -> SupabaseSession:
        raise InvalidCredentialsError("bad creds")

    harness.app.state.supabase_client.password_login = fake_login

    response = harness.client.post(
        "/login", data={"email": "x@x.com", "password": "wrong"}, follow_redirects=False
    )

    assert response.status_code == 200
    assert response.cookies.get(SESSION_COOKIE_NAME) is None
    assert "invalidos" in response.text


def test_logout_clears_cookie_and_redirects(harness) -> None:
    response = harness.client.post("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"

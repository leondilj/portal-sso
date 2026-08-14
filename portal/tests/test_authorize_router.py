from app.sessions import SessionData


def _session(acessos: dict) -> SessionData:
    return SessionData(
        user_id="user-1",
        email="joao@lab.internal",
        access_token="tok-acesso",
        refresh_token="tok-refresh",
        acessos=acessos,
    )


def test_authorize_denies_app_not_in_acessos(harness) -> None:
    harness.set_session(_session({"vendas": ["analista"]}))

    response = harness.client.get("/authorize", params={"app_id": "qualidade"})

    assert response.status_code == 403


def test_authorize_success_issues_code_and_redirects(harness, fake_pool) -> None:
    harness.set_session(_session({"qualidade": ["gerente"]}))

    response = harness.client.get(
        "/authorize", params={"app_id": "qualidade"}, follow_redirects=False
    )

    assert response.status_code == 302
    location = response.headers["location"]
    assert location.startswith("http://qualidade.lab.internal/callback?code=")
    code = location.split("code=", 1)[1]

    row = fake_pool.auth_codes[code]
    assert row["user_id"] == "user-1"
    assert row["aplicacao_id"] == "qualidade"
    assert row["access_token"] == "tok-acesso"
    assert row["refresh_token"] == "tok-refresh"
    assert row["usado_em"] is None


def test_authorize_app_without_client_registered_returns_502(harness) -> None:
    harness.set_session(_session({"vendas": ["analista"]}))

    response = harness.client.get("/authorize", params={"app_id": "vendas"})

    assert response.status_code == 502

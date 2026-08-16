from app.sessions import SessionData


def _session(acessos: dict) -> SessionData:
    return SessionData(
        user_id="user-1",
        email="joao@lab.internal",
        access_token="tok",
        refresh_token="ref",
        acessos=acessos,
    )


def test_home_without_session_redirects_to_login(harness) -> None:
    response = harness.client.get("/", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_home_lists_only_accessible_active_apps_in_order(harness) -> None:
    harness.set_session(
        _session({"qualidade": ["gerente"], "vendas": ["analista"], "inativa": ["operador"]})
    )

    response = harness.client.get("/")

    assert response.status_code == 200
    body = response.text
    assert "Qualidade" in body
    assert "Vendas" in body
    assert "Inativa" not in body
    # Qualidade (ordem=1) deve aparecer antes de Vendas (ordem=2)
    assert body.index("Qualidade") < body.index("Vendas")


def test_home_app_without_client_credentials_is_not_shown_as_tile(harness) -> None:
    """Regressao: uma aplicacao presente em acessos e ativa, mas sem linha
    em app_clients (ex.: o proprio 'portal', que nao e um cliente OAuth
    redirecionado via /authorize), nao deve aparecer como tile clicavel -
    clicar levaria a um 502 em /authorize."""
    harness.set_session(_session({"qualidade": ["gerente"], "semcliente": ["algo"]}))

    response = harness.client.get("/")

    assert response.status_code == 200
    assert "Qualidade" in response.text
    assert "SemCliente" not in response.text


def test_home_empty_acessos_shows_empty_state(harness) -> None:
    harness.set_session(_session({}))

    response = harness.client.get("/")

    assert response.status_code == 200
    assert "nao tem acesso" in response.text

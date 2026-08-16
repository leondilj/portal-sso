from app.sessions import SessionData


def _admin_session() -> SessionData:
    return SessionData(
        user_id="admin-1",
        email="admin@lab.internal",
        access_token="t",
        refresh_token="r",
        acessos={"portal": ["admin"]},
    )


def test_configurar_novo_cliente_gera_secret_e_revela_uma_vez(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/sistemas/inativa/cliente/novo",
        data={"redirect_uri": "http://inativa.lab.internal/callback"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sistemas/inativa/cliente/segredo"
    assert fake_pool.app_clients["inativa"]["redirect_uris"] == [
        "http://inativa.lab.internal/callback"
    ]

    reveal = harness.client.get(response.headers["location"])
    assert "Client secret gerado" in reveal.text

    reveal_again = harness.client.get("/admin/sistemas/inativa/cliente/segredo")
    assert "Nada para exibir" in reveal_again.text


def test_configurar_novo_cliente_ja_configurado_redireciona_para_detalhe(harness) -> None:
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade/cliente/novo", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sistemas/qualidade"


def test_editar_redirect_uri_nao_altera_secret(harness, fake_pool) -> None:
    harness.set_session(_admin_session())
    secret_antes = fake_pool.app_clients["qualidade"]["client_secret"]

    response = harness.client.post(
        "/admin/sistemas/qualidade/cliente/editar",
        data={"redirect_uri": "http://qualidade.lab.internal/novo-callback"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_pool.app_clients["qualidade"]["redirect_uris"] == [
        "http://qualidade.lab.internal/novo-callback"
    ]
    assert fake_pool.app_clients["qualidade"]["client_secret"] == secret_antes


def test_regenerar_secret_muda_o_valor(harness, fake_pool) -> None:
    harness.set_session(_admin_session())
    secret_antes = fake_pool.app_clients["qualidade"]["client_secret"]

    response = harness.client.post(
        "/admin/sistemas/qualidade/cliente/regenerar", follow_redirects=False
    )

    assert response.status_code == 303
    reveal = harness.client.get(response.headers["location"])
    assert "Client secret regenerado" in reveal.text
    assert fake_pool.app_clients["qualidade"]["client_secret"] != secret_antes
    # redirect_uris preservadas - regenerar nao deve mexer nelas
    assert fake_pool.app_clients["qualidade"]["redirect_uris"] == [
        "http://qualidade.lab.internal/callback"
    ]


def test_regenerar_sem_cliente_configurado_404(harness) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/sistemas/inativa/cliente/regenerar")

    assert response.status_code == 404

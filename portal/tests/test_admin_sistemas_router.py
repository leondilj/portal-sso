from app.sessions import SessionData


def _admin_session() -> SessionData:
    return SessionData(
        user_id="admin-1",
        email="admin@lab.internal",
        access_token="t",
        refresh_token="r",
        acessos={"portal": ["admin"]},
    )


def test_listar_sistemas(harness) -> None:
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas")

    assert response.status_code == 200
    assert "Qualidade" in response.text


def test_criar_sistema_sucesso(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/sistemas/novo",
        data={"aplicacao_id": "novo-app", "nome": "Novo App", "url": "http://novo", "ordem": "5"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sistemas/novo-app"
    assert fake_pool.aplicacoes["novo-app"]["nome"] == "Novo App"
    assert fake_pool.aplicacoes["novo-app"]["ativo"] is True


def test_criar_sistema_duplicado_reexibe_formulario(harness) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/sistemas/novo",
        data={"aplicacao_id": "qualidade", "nome": "Duplicado", "url": "http://x", "ordem": "0"},
    )

    assert response.status_code == 200
    assert "ja existe" in response.text.lower()


def test_detalhe_sistema_inexistente_404(harness) -> None:
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/nao-existe")

    assert response.status_code == 404


def test_detalhe_mostra_cliente_e_perfis(harness) -> None:
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade")

    assert response.status_code == 200
    assert "Configurado" in response.text


def test_atualizar_sistema(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/sistemas/qualidade",
        data={
            "nome": "Qualidade Atualizada",
            "url": "http://qualidade.lab.internal",
            "ordem": "1",
        },
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_pool.aplicacoes["qualidade"]["nome"] == "Qualidade Atualizada"


def test_desativar_e_reativar_sistema(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/sistemas/qualidade/desativar", follow_redirects=False)
    assert response.status_code == 303
    assert fake_pool.aplicacoes["qualidade"]["ativo"] is False

    response = harness.client.post("/admin/sistemas/qualidade/ativar", follow_redirects=False)
    assert response.status_code == 303
    assert fake_pool.aplicacoes["qualidade"]["ativo"] is True

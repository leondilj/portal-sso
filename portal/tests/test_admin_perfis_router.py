from datetime import UTC, datetime

from app.sessions import SessionData


def _admin_session() -> SessionData:
    return SessionData(
        user_id="admin-1",
        email="admin@lab.internal",
        access_token="t",
        refresh_token="r",
        acessos={"portal": ["admin"]},
    )


def _seed_papel(fake_pool, *, aplicacao_id: str, codigo: str, nome: str = "Papel") -> str:
    import uuid

    papel_id = str(uuid.uuid4())
    fake_pool.papeis[papel_id] = {
        "id": papel_id,
        "aplicacao_id": aplicacao_id,
        "codigo": codigo,
        "nome": nome,
        "descricao": None,
        "criado_em": datetime.now(UTC),
    }
    return papel_id


def test_listar_perfis(harness, fake_pool) -> None:
    _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade/perfis")

    assert response.status_code == 200
    assert "gerente" in response.text.lower()


def test_criar_perfil(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/sistemas/qualidade/perfis/novo",
        data={"codigo": "analista", "nome": "Analista"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert any(p["codigo"] == "analista" for p in fake_pool.papeis.values())


def test_criar_perfil_duplicado_reexibe_formulario(harness, fake_pool) -> None:
    _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/sistemas/qualidade/perfis/novo",
        data={"codigo": "gerente", "nome": "Outro nome"},
    )

    assert response.status_code == 200
    assert "ja existe" in response.text.lower()


def test_editar_perfil_nao_altera_codigo(harness, fake_pool) -> None:
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    harness.set_session(_admin_session())

    response = harness.client.post(
        f"/admin/sistemas/qualidade/perfis/{papel_id}/editar",
        data={"nome": "Gerente Senior", "descricao": "novo"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert fake_pool.papeis[papel_id]["nome"] == "Gerente Senior"
    assert fake_pool.papeis[papel_id]["codigo"] == "gerente"


def test_excluir_confirmar_mostra_contagem_de_usuarios(harness, fake_pool) -> None:
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    fake_pool.usuario_papeis[("user-x", papel_id)] = {
        "user_id": "user-x",
        "papel_id": papel_id,
        "concedido_por": "admin-1",
        "concedido_em": datetime.now(UTC),
    }
    harness.set_session(_admin_session())

    response = harness.client.get(f"/admin/sistemas/qualidade/perfis/{papel_id}/excluir")

    assert response.status_code == 200
    assert "1 usuario" in response.text.lower()


def test_excluir_perfil(harness, fake_pool) -> None:
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    harness.set_session(_admin_session())

    response = harness.client.post(
        f"/admin/sistemas/qualidade/perfis/{papel_id}/excluir", follow_redirects=False
    )

    assert response.status_code == 303
    assert papel_id not in fake_pool.papeis

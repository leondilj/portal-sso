import uuid
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


def _seed_user(fake_pool, *, user_id: str, email: str, nome: str | None = None) -> None:
    fake_pool.auth_users[user_id] = {
        "id": user_id,
        "email": email,
        "created_at": datetime.now(UTC),
        "last_sign_in_at": None,
        "email_confirmed_at": datetime.now(UTC),
    }
    if nome is not None:
        fake_pool.profiles[user_id] = {"id": user_id, "nome": nome}


def _seed_papel(fake_pool, *, aplicacao_id: str, codigo: str, nome: str = "Papel") -> str:
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


def _grant(fake_pool, *, user_id: str, papel_id: str) -> None:
    fake_pool.usuario_papeis[(user_id, papel_id)] = {
        "user_id": user_id,
        "papel_id": papel_id,
        "concedido_por": "admin-1",
        "concedido_em": datetime.now(UTC),
    }


def test_listar_usuarios_do_sistema(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal", nome="Joao Silva")
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    _grant(fake_pool, user_id="u1", papel_id=papel_id)
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade/usuarios")

    assert response.status_code == 200
    assert "Joao Silva" in response.text
    assert "gerente" in response.text.lower()


def test_listar_usuarios_do_sistema_ignora_outros_sistemas(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")
    _seed_user(fake_pool, user_id="u2", email="maria@lab.internal")
    papel_qualidade = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    papel_vendas = _seed_papel(fake_pool, aplicacao_id="vendas", codigo="analista")
    _grant(fake_pool, user_id="u1", papel_id=papel_qualidade)
    _grant(fake_pool, user_id="u2", papel_id=papel_vendas)
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade/usuarios")

    assert response.status_code == 200
    assert "joao@lab.internal" in response.text
    assert "maria@lab.internal" not in response.text


def test_listar_usuarios_sem_nome_mostra_email(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    _grant(fake_pool, user_id="u1", papel_id=papel_id)
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade/usuarios")

    assert response.status_code == 200
    assert "joao@lab.internal" in response.text


def test_sistema_sem_usuarios_mostra_estado_vazio(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/qualidade/usuarios")

    assert response.status_code == 200
    assert "nenhum usuario" in response.text.lower()


def test_revogar_papel_pela_tela_do_sistema(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    _grant(fake_pool, user_id="u1", papel_id=papel_id)
    harness.set_session(_admin_session())

    response = harness.client.post(
        f"/admin/sistemas/qualidade/usuarios/u1/papeis/{papel_id}/revogar",
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/sistemas/qualidade/usuarios"
    assert ("u1", papel_id) not in fake_pool.usuario_papeis


def test_sistema_inexistente_404(harness, fake_pool) -> None:
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/sistemas/nao-existe/usuarios")

    assert response.status_code == 404

import uuid
from datetime import UTC, datetime

from app.sessions import SessionData
from app.supabase_admin_client import (
    AdminApiError,
    AdminCreatedUser,
    EmailAlreadyExistsError,
    WeakPasswordError,
)


def _admin_session(user_id: str = "admin-1") -> SessionData:
    return SessionData(
        user_id=user_id,
        email="admin@lab.internal",
        access_token="t",
        refresh_token="r",
        acessos={"portal": ["admin"]},
    )


def _seed_user(fake_pool, *, user_id: str, email: str) -> None:
    fake_pool.auth_users[user_id] = {
        "id": user_id,
        "email": email,
        "created_at": datetime.now(UTC),
        "last_sign_in_at": None,
        "email_confirmed_at": datetime.now(UTC),
    }


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


def test_buscar_sem_query_nao_lista_ninguem(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/usuarios")

    assert response.status_code == 200
    assert "joao@lab.internal" not in response.text


def test_buscar_com_query(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")
    harness.set_session(_admin_session())

    response = harness.client.get("/admin/usuarios", params={"q": "joao"})

    assert response.status_code == 200
    assert "joao@lab.internal" in response.text


def test_criar_usuario_sucesso_revela_senha_uma_vez(harness, fake_pool) -> None:
    async def fake_create_user(
        *, email: str, password: str, nome: str | None = None
    ) -> AdminCreatedUser:
        assert email == "novo@lab.internal"
        _seed_user(fake_pool, user_id="new-user-1", email=email)
        return AdminCreatedUser(id="new-user-1", email=email)

    harness.app.state.supabase_admin_client.create_user = fake_create_user
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/usuarios/novo", data={"email": "novo@lab.internal"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/usuarios/new-user-1/segredo"

    reveal = harness.client.get(response.headers["location"])
    assert "senha inicial" in reveal.text.lower()

    reveal_again = harness.client.get("/admin/usuarios/new-user-1/segredo")
    assert "nada para exibir" in reveal_again.text.lower()


def test_criar_usuario_email_duplicado(harness) -> None:
    async def fake_create_user(
        *, email: str, password: str, nome: str | None = None
    ) -> AdminCreatedUser:
        raise EmailAlreadyExistsError(email)

    harness.app.state.supabase_admin_client.create_user = fake_create_user
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/usuarios/novo", data={"email": "existe@lab.internal"})

    assert response.status_code == 200
    assert "ja existe" in response.text.lower()


def test_criar_usuario_senha_gerada_rejeitada(harness) -> None:
    async def fake_create_user(
        *, email: str, password: str, nome: str | None = None
    ) -> AdminCreatedUser:
        raise WeakPasswordError(["muito curta"])

    harness.app.state.supabase_admin_client.create_user = fake_create_user
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/usuarios/novo", data={"email": "x@lab.internal"})

    assert response.status_code == 200
    assert "muito curta" in response.text


def test_criar_usuario_erro_generico(harness) -> None:
    async def fake_create_user(
        *, email: str, password: str, nome: str | None = None
    ) -> AdminCreatedUser:
        raise AdminApiError("boom")

    harness.app.state.supabase_admin_client.create_user = fake_create_user
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/usuarios/novo", data={"email": "x@lab.internal"})

    assert response.status_code == 200
    assert "erro ao criar" in response.text.lower()


def test_criar_usuario_com_papel_inicial_concede_direto(harness, fake_pool) -> None:
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="analista")

    async def fake_create_user(
        *, email: str, password: str, nome: str | None = None
    ) -> AdminCreatedUser:
        _seed_user(fake_pool, user_id="new-user-2", email=email)
        return AdminCreatedUser(id="new-user-2", email=email)

    harness.app.state.supabase_admin_client.create_user = fake_create_user
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/usuarios/novo",
        data={"email": "com-papel@lab.internal", "papel_inicial": papel_id},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert ("new-user-2", papel_id) in fake_pool.usuario_papeis


def test_conceder_e_revogar_papel(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")
    papel_id = _seed_papel(fake_pool, aplicacao_id="qualidade", codigo="gerente")
    harness.set_session(_admin_session())

    response = harness.client.post(
        "/admin/usuarios/u1/papeis/conceder", data={"papel_id": papel_id}, follow_redirects=False
    )
    assert response.status_code == 303
    assert ("u1", papel_id) in fake_pool.usuario_papeis
    assert fake_pool.usuario_papeis[("u1", papel_id)]["concedido_por"] == "admin-1"

    response = harness.client.post(
        f"/admin/usuarios/u1/papeis/{papel_id}/revogar", follow_redirects=False
    )
    assert response.status_code == 303
    assert ("u1", papel_id) not in fake_pool.usuario_papeis


def test_revogar_ultimo_admin_e_bloqueado(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="only-admin", email="admin@lab.internal")
    admin_papel_id = _seed_papel(
        fake_pool, aplicacao_id="portal", codigo="admin", nome="Administrador"
    )
    fake_pool.usuario_papeis[("only-admin", admin_papel_id)] = {
        "user_id": "only-admin",
        "papel_id": admin_papel_id,
        "concedido_por": "only-admin",
        "concedido_em": datetime.now(UTC),
    }
    harness.set_session(_admin_session(user_id="only-admin"))

    response = harness.client.post(f"/admin/usuarios/only-admin/papeis/{admin_papel_id}/revogar")

    assert response.status_code == 200
    assert "ultimo administrador" in response.text.lower()
    assert ("only-admin", admin_papel_id) in fake_pool.usuario_papeis


def test_revogar_admin_permitido_quando_ha_outro(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="admin-a", email="a@lab.internal")
    _seed_user(fake_pool, user_id="admin-b", email="b@lab.internal")
    admin_papel_id = _seed_papel(
        fake_pool, aplicacao_id="portal", codigo="admin", nome="Administrador"
    )
    fake_pool.usuario_papeis[("admin-a", admin_papel_id)] = {
        "user_id": "admin-a",
        "papel_id": admin_papel_id,
        "concedido_por": "admin-a",
        "concedido_em": datetime.now(UTC),
    }
    fake_pool.usuario_papeis[("admin-b", admin_papel_id)] = {
        "user_id": "admin-b",
        "papel_id": admin_papel_id,
        "concedido_por": "admin-a",
        "concedido_em": datetime.now(UTC),
    }
    harness.set_session(_admin_session(user_id="admin-a"))

    response = harness.client.post(
        f"/admin/usuarios/admin-b/papeis/{admin_papel_id}/revogar", follow_redirects=False
    )

    assert response.status_code == 303
    assert ("admin-b", admin_papel_id) not in fake_pool.usuario_papeis


def test_redefinir_senha(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")

    async def fake_reset_password(*, user_id: str, new_password: str) -> None:
        assert user_id == "u1"

    harness.app.state.supabase_admin_client.reset_password = fake_reset_password
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/usuarios/u1/redefinir-senha", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/admin/usuarios/u1/segredo"

    reveal = harness.client.get(response.headers["location"])
    assert "senha redefinida" in reveal.text.lower()


def test_redefinir_senha_erro(harness, fake_pool) -> None:
    _seed_user(fake_pool, user_id="u1", email="joao@lab.internal")

    async def fake_reset_password(*, user_id: str, new_password: str) -> None:
        raise AdminApiError("boom")

    harness.app.state.supabase_admin_client.reset_password = fake_reset_password
    harness.set_session(_admin_session())

    response = harness.client.post("/admin/usuarios/u1/redefinir-senha")

    assert response.status_code == 200
    assert "erro ao redefinir" in response.text.lower()

import asyncio
from datetime import UTC, datetime, timedelta

from app import db


def _seed_code(
    fake_pool,
    *,
    code: str = "code-1",
    expira_em: datetime | None = None,
    usado_em: datetime | None = None,
) -> str:
    fake_pool.auth_codes[code] = {
        "code": code,
        "user_id": "user-1",
        "aplicacao_id": "qualidade",
        "redirect_uri": "http://qualidade.lab.internal/callback",
        "access_token": "tok-acesso",
        "refresh_token": "tok-refresh",
        "expira_em": expira_em or (datetime.now(UTC) + timedelta(seconds=60)),
        "usado_em": usado_em,
    }
    return code


def test_token_happy_path_then_already_used(harness, fake_pool) -> None:
    code = _seed_code(fake_pool)

    first = harness.client.post("/token", data={"code": code, "client_secret": "segredo-certo"})
    assert first.status_code == 200
    assert first.json() == {"access_token": "tok-acesso", "refresh_token": "tok-refresh"}

    second = harness.client.post("/token", data={"code": code, "client_secret": "segredo-certo"})
    assert second.status_code == 400
    assert second.json() == {"error": "already_used"}


def test_token_json_body_also_accepted(harness, fake_pool) -> None:
    code = _seed_code(fake_pool)

    response = harness.client.post(
        "/token", json={"code": code, "client_secret": "segredo-certo"}
    )

    assert response.status_code == 200


def test_token_wrong_secret_does_not_burn_code(harness, fake_pool) -> None:
    code = _seed_code(fake_pool)

    response = harness.client.post("/token", data={"code": code, "client_secret": "chute-errado"})

    assert response.status_code == 401
    assert response.json() == {"error": "invalid_client"}
    assert fake_pool.auth_codes[code]["usado_em"] is None

    retry = harness.client.post("/token", data={"code": code, "client_secret": "segredo-certo"})
    assert retry.status_code == 200


def test_token_expired_code(harness, fake_pool) -> None:
    code = _seed_code(fake_pool, expira_em=datetime.now(UTC) - timedelta(seconds=1))

    response = harness.client.post("/token", data={"code": code, "client_secret": "segredo-certo"})

    assert response.status_code == 400
    assert response.json() == {"error": "expired"}


def test_token_unknown_code(harness) -> None:
    response = harness.client.post(
        "/token", data={"code": "nao-existe", "client_secret": "segredo-certo"}
    )

    assert response.status_code == 400
    assert response.json() == {"error": "invalid_grant"}


async def test_consume_auth_code_concurrent_only_one_wins(fake_pool) -> None:
    """Simula, contra o fake pool (que emula `for update` com um lock),
    duas trocas concorrentes do mesmo code. So uma pode vencer - a outra
    tem que ver o code ja usado. Concorrencia real de linha do Postgres
    fica para validacao manual na VM do lab."""
    code = _seed_code(fake_pool, code="concurrent-code")

    results = await asyncio.gather(
        db.consume_auth_code(fake_pool, code, "segredo-certo"),
        db.consume_auth_code(fake_pool, code, "segredo-certo"),
        return_exceptions=True,
    )

    successes = [r for r in results if not isinstance(r, Exception)]
    failures = [r for r in results if isinstance(r, Exception)]
    assert len(successes) == 1
    assert len(failures) == 1
    assert isinstance(failures[0], db.AuthCodeAlreadyUsedError)

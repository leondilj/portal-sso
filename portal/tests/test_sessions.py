import time

from app.sessions import SessionData, SessionManager


def _session() -> SessionData:
    return SessionData(
        user_id="user-1",
        email="joao@lab.internal",
        access_token="tok-abc",
        refresh_token="ref-abc",
        acessos={"qualidade": ["gerente"]},
    )


def test_roundtrip() -> None:
    manager = SessionManager(secret="s3cr3t", max_age_seconds=3600)
    cookie_value = manager.encode(_session())

    decoded = manager.decode(cookie_value)

    assert decoded == _session()


def test_tampered_cookie_returns_none() -> None:
    manager = SessionManager(secret="s3cr3t", max_age_seconds=3600)
    cookie_value = manager.encode(_session())

    assert manager.decode(cookie_value[:-1] + ("A" if cookie_value[-1] != "A" else "B")) is None


def test_expired_cookie_returns_none() -> None:
    manager = SessionManager(secret="s3cr3t", max_age_seconds=0)
    cookie_value = manager.encode(_session())
    time.sleep(1.1)

    assert manager.decode(cookie_value) is None


def test_wrong_secret_returns_none() -> None:
    cookie_value = SessionManager(secret="s3cr3t", max_age_seconds=3600).encode(_session())

    assert SessionManager(secret="outro-secret", max_age_seconds=3600).decode(cookie_value) is None

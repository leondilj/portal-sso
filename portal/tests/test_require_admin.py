from app.sessions import SessionData


def _session(acessos: dict) -> SessionData:
    return SessionData(
        user_id="user-1",
        email="joao@lab.internal",
        access_token="t",
        refresh_token="r",
        acessos=acessos,
    )


def test_admin_without_session_redirects_to_login(harness) -> None:
    response = harness.client.get("/admin", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_admin_session_without_admin_role_returns_403(harness) -> None:
    harness.set_session(_session({"qualidade": ["gerente"]}))

    response = harness.client.get("/admin")

    assert response.status_code == 403


def test_admin_session_with_other_apps_but_no_portal_role_returns_403(harness) -> None:
    harness.set_session(_session({"portal": ["outro-papel"]}))

    response = harness.client.get("/admin")

    assert response.status_code == 403


def test_admin_session_with_admin_role_passes(harness) -> None:
    harness.set_session(_session({"portal": ["admin"]}))

    response = harness.client.get("/admin")

    assert response.status_code == 200

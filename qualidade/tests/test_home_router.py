from app.sessions import SessionData


def _session(papeis: list[str]) -> SessionData:
    return SessionData(user_id="user-1", email="joao@lab.internal", papeis=papeis)


def test_home_without_session_shows_not_logged_in(harness) -> None:
    response = harness.client.get("/")

    assert response.status_code == 200
    assert "nao esta logado" in response.text


def test_home_analista_has_no_gerente_link(harness) -> None:
    harness.set_session(_session(["analista"]))

    response = harness.client.get("/")

    assert response.status_code == 200
    assert "analista" in response.text
    assert "/area-gerente" not in response.text


def test_home_gerente_has_gerente_link(harness) -> None:
    harness.set_session(_session(["gerente"]))

    response = harness.client.get("/")

    assert response.status_code == 200
    assert "/area-gerente" in response.text


def test_area_gerente_denies_without_session(harness) -> None:
    response = harness.client.get("/area-gerente")

    assert response.status_code == 403


def test_area_gerente_denies_analista(harness) -> None:
    harness.set_session(_session(["analista"]))

    response = harness.client.get("/area-gerente")

    assert response.status_code == 403


def test_area_gerente_allows_gerente(harness) -> None:
    harness.set_session(_session(["gerente"]))

    response = harness.client.get("/area-gerente")

    assert response.status_code == 200


def test_logout_clears_cookie_and_redirects(harness) -> None:
    harness.set_session(_session(["gerente"]))

    response = harness.client.get("/logout", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/"

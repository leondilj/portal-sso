import httpx
import pytest
import respx

from app.supabase_admin_client import (
    AdminApiError,
    EmailAlreadyExistsError,
    SupabaseAdminClient,
    WeakPasswordError,
)

_USER_ID = "b0801f26-fd36-4c05-a1bc-8335552e76c1"
_USERS_URL = "http://supabase.test/auth/v1/admin/users"
_USER_BODY = {
    "id": "user-123",
    "email": "novo@lab.internal",
    "aud": "authenticated",
    "role": "authenticated",
    "app_metadata": {},
    "user_metadata": {},
    "identities": [],
    "created_at": "2026-01-01T00:00:00Z",
    "updated_at": "2026-01-01T00:00:00Z",
}


async def test_create_user_success() -> None:
    with respx.mock:
        route = respx.post(_USERS_URL).mock(return_value=httpx.Response(200, json=_USER_BODY))
        client = SupabaseAdminClient("http://supabase.test", "service-role-key")
        result = await client.create_user(email="novo@lab.internal", password="s3nh4-forte")

    assert result.id == "user-123"
    assert result.email == "novo@lab.internal"
    sent = route.calls.last.request
    assert sent.headers["apikey"] == "service-role-key"


async def test_create_user_with_nome_envia_user_metadata() -> None:
    with respx.mock:
        route = respx.post(_USERS_URL).mock(return_value=httpx.Response(200, json=_USER_BODY))
        client = SupabaseAdminClient("http://supabase.test", "service-role-key")
        await client.create_user(email="novo@lab.internal", password="s3nh4-forte", nome="Joao")

    sent = route.calls.last.request
    assert b'"user_metadata":{"nome":"Joao"}' in sent.content


async def test_create_user_duplicate_email() -> None:
    with respx.mock:
        respx.post(_USERS_URL).mock(
            return_value=httpx.Response(422, json={"error_code": "email_exists", "msg": "dup"})
        )
        client = SupabaseAdminClient("http://supabase.test", "k")
        with pytest.raises(EmailAlreadyExistsError):
            await client.create_user(email="dup@lab.internal", password="x")


async def test_create_user_weak_password() -> None:
    with respx.mock:
        respx.post(_USERS_URL).mock(
            return_value=httpx.Response(
                422,
                json={
                    "error_code": "weak_password",
                    "msg": "weak",
                    "weak_password": {"reasons": ["length"]},
                },
            )
        )
        client = SupabaseAdminClient("http://supabase.test", "k")
        with pytest.raises(WeakPasswordError) as exc_info:
            await client.create_user(email="x@lab.internal", password="123")

    assert exc_info.value.reasons == ["length"]


async def test_create_user_generic_error() -> None:
    with respx.mock:
        respx.post(_USERS_URL).mock(return_value=httpx.Response(500, json={"msg": "boom"}))
        client = SupabaseAdminClient("http://supabase.test", "k")
        with pytest.raises(AdminApiError):
            await client.create_user(email="x@lab.internal", password="123")


async def test_reset_password_success() -> None:
    with respx.mock:
        route = respx.put(f"{_USERS_URL}/{_USER_ID}").mock(
            return_value=httpx.Response(200, json=_USER_BODY)
        )
        client = SupabaseAdminClient("http://supabase.test", "k")
        await client.reset_password(user_id=_USER_ID, new_password="nova-senha-forte")

    body = route.calls.last.request.content
    assert b"nova-senha-forte" in body


async def test_reset_password_weak_password() -> None:
    with respx.mock:
        respx.put(f"{_USERS_URL}/{_USER_ID}").mock(
            return_value=httpx.Response(
                422,
                json={
                    "error_code": "weak_password",
                    "msg": "weak",
                    "weak_password": {"reasons": ["too_short"]},
                },
            )
        )
        client = SupabaseAdminClient("http://supabase.test", "k")
        with pytest.raises(WeakPasswordError):
            await client.reset_password(user_id=_USER_ID, new_password="123")

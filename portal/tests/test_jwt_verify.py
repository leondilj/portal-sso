from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

from app.jwt_verify import InvalidTokenError, JWKSVerifier, extract_acessos, extract_nome


@pytest.fixture
def verifier(ec_keys) -> JWKSVerifier:
    _, public_key = ec_keys
    v = JWKSVerifier("http://unused.invalid/jwks.json")
    v._jwk_client = SimpleNamespace(
        get_signing_key_from_jwt=lambda token: SimpleNamespace(key=public_key)
    )
    return v


def test_valid_token_decodes_with_acessos(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt(
        {"app_metadata": {"acessos": {"qualidade": ["gerente"], "vendas": ["analista"]}}}
    )

    claims = verifier.verify(token)

    assert claims["sub"] == "user-1"
    assert extract_acessos(claims) == {"qualidade": ["gerente"], "vendas": ["analista"]}


def test_wrong_signature_rejected(verifier: JWKSVerifier, ec_keys, sign_jwt) -> None:
    import jwt as pyjwt
    from cryptography.hazmat.primitives.asymmetric import ec as ec_mod

    other_private_key = ec_mod.generate_private_key(ec_mod.SECP256R1())
    token = pyjwt.encode(
        {
            "sub": "user-1",
            "aud": "authenticated",
            "exp": datetime.now(UTC) + timedelta(minutes=30),
        },
        other_private_key,
        algorithm="ES256",
    )

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)


def test_expired_token_rejected(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt(exp=datetime.now(UTC) - timedelta(minutes=1))

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)


def test_wrong_audience_rejected(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt(aud="outra-audience")

    with pytest.raises(InvalidTokenError):
        verifier.verify(token)


def test_missing_app_metadata_yields_empty_acessos(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt({})

    claims = verifier.verify(token)

    assert extract_acessos(claims) == {}


def test_extract_nome_le_user_metadata(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt({"user_metadata": {"nome": "Joao Silva"}})

    claims = verifier.verify(token)

    assert extract_nome(claims) == "Joao Silva"


def test_extract_nome_ausente_retorna_none(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt({})

    claims = verifier.verify(token)

    assert extract_nome(claims) is None


def test_extract_nome_vazio_retorna_none(verifier: JWKSVerifier, sign_jwt) -> None:
    token = sign_jwt({"user_metadata": {"nome": "   "}})

    claims = verifier.verify(token)

    assert extract_nome(claims) is None

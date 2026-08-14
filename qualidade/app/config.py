from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    portal_token_url: str
    qualidade_client_secret: str

    supabase_jwks_url: str

    qualidade_session_secret: str
    qualidade_session_max_age_seconds: int = 1800
    qualidade_cookie_secure: bool = False

    qualidade_host: str = "0.0.0.0"
    qualidade_port: int = 8081

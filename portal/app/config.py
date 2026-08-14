from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    supabase_url: str
    supabase_publishable_key: str
    supabase_jwks_url: str

    portal_database_url: str

    portal_session_secret: str
    portal_session_max_age_seconds: int = 1800
    portal_cookie_secure: bool = False

    portal_auth_code_ttl_seconds: int = 60

    portal_host: str = "0.0.0.0"
    portal_port: int = 8080

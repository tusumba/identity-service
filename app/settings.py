from pydantic import SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    service_name: str = "identity"
    environment: str = "local"
    log_level: str = "INFO"
    log_json: bool = True

    database_url: SecretStr
    database_pool_size: int = 5
    database_echo: bool = False

    # Закрытый ключ Identity (PEM, допустим вид с \n одной строкой). Публичный ключ для
    # остальных сервисов задаётся переменной JWT_PUBLIC_KEY (tusumba-common).
    jwt_private_key: SecretStr
    access_token_ttl_seconds: int = 900
    refresh_token_ttl_seconds: int = 2_592_000

    @field_validator("database_url")
    @classmethod
    def _require_asyncpg(cls, value: SecretStr) -> SecretStr:
        if not value.get_secret_value().startswith("postgresql+asyncpg://"):
            raise ValueError("DATABASE_URL must start with postgresql+asyncpg://")
        return value

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    database_url: str = "postgresql+asyncpg://acciassist:change-me-in-prod@db:5432/acciassist"
    jwt_secret: str = "dev-only-insecure-secret-change-me"
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:8082"

    admin_email: str = "admin@acciassist.com"
    admin_password: str = "changeme123"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

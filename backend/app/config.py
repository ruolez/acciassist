from pydantic import model_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

_DEV_JWT_SECRET = "dev-only-insecure-secret-change-me"
_DEV_ADMIN_PASSWORD = "changeme123"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    app_env: str = "development"
    database_url: str = "postgresql+asyncpg://acciassist:change-me-in-prod@db:5432/acciassist"
    jwt_secret: str = _DEV_JWT_SECRET
    jwt_expire_minutes: int = 720
    cors_origins: str = "http://localhost:8082"

    admin_email: str = "admin@acciassist.com"
    admin_password: str = _DEV_ADMIN_PASSWORD

    # Mark the admin session cookie Secure (send only over HTTPS). Enabled by
    # the installer when SSL is configured; off in dev/HTTP.
    cookie_secure: bool = False

    # In-process rate limiting for login/lead/intake endpoints; tests disable it.
    rate_limit_enabled: bool = True

    # Client document uploads (case files: bills, records, photos).
    upload_dir: str = "/data/uploads"
    max_upload_mb: int = 15
    max_documents_per_case: int = 30

    @property
    def is_production(self) -> bool:
        return self.app_env == "production"

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]

    @model_validator(mode="after")
    def _refuse_insecure_production(self) -> "Settings":
        if not self.is_production:
            return self
        problems = []
        if self.jwt_secret == _DEV_JWT_SECRET or len(self.jwt_secret) < 32:
            problems.append("JWT_SECRET is the dev default or shorter than 32 characters")
        if self.admin_password == _DEV_ADMIN_PASSWORD:
            problems.append("ADMIN_PASSWORD is the dev default")
        if "change-me-in-prod" in self.database_url:
            problems.append("DATABASE_URL contains the dev default password")
        if problems:
            raise ValueError(
                "Refusing to start with APP_ENV=production and insecure settings: "
                + "; ".join(problems)
            )
        return self


settings = Settings()

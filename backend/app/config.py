from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    # SQLAlchemy URL. Local dev reuses the same Postgres cluster as SharpRight
    # via a dedicated database; production gets its own database (and, from
    # Phase 1, the `postgis` extension - see docs/BLUEPRINT.md sec 14).
    database_url: str = (
        "postgresql+psycopg://sharpright:sharpright_dev@127.0.0.1:5432/trailkeeper"
    )

    # Auth. jwt_secret MUST be overridden in every real deployment.
    jwt_secret: str = "dev-insecure-change-me"
    jwt_algorithm: str = "HS256"
    access_token_ttl_minutes: int = 30
    refresh_token_ttl_days: int = 30

    # Open registration bootstraps the first organisation (a user signs up and
    # becomes its owner). Turn this off once the org exists; further members
    # then join only through an invite.
    allow_registration: bool = True
    invite_ttl_days: int = 14

    # Comma-separated origins for the web console (Phase 6). Empty -> no CORS.
    cors_origins: str = ""

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

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

    # Task photos, saved to local disk (see docs/BLUEPRINT.md sec 16 - MinIO
    # is the upgrade path if this ever gets awkward; plain files are fine at
    # this scale and need zero extra services). Relative paths resolve
    # against the backend/ working directory.
    upload_dir: str = "data/uploads"
    max_upload_mb: int = 15

    # How far (metres) a task's GPS point may be from a trail line to still
    # auto-attach to it. Beyond this, nearest_trail_id is left null.
    nearest_trail_max_m: float = 75.0

    @property
    def cors_origin_list(self) -> list[str]:
        return [o.strip() for o in self.cors_origins.split(",") if o.strip()]


settings = Settings()

from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_prefix="MIGRATION_AGENT_",
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
    )

    # Core
    env: str = Field(default="dev", description="Runtime environment: dev, staging, prod")
    secret_key: str = Field(..., description="App secret key; must be set in all envs")

    # Database
    database_url: str = Field(
        ...,
        description="Async SQLAlchemy database URL (postgresql+asyncpg://...)",
    )

    # Supabase
    supabase_url: str = Field(default="", description="Supabase project URL")
    supabase_anon_key: str = Field(default="", description="Supabase anon key for realtime only")

    # Slack
    slack_bot_token: str = Field(default="", description="xoxb- bot token")
    slack_signing_secret: str = Field(
        default="", description="Signing secret for request verification"
    )
    slack_app_token: str = Field(default="", description="xapp- token for socket mode")

    # Anthropic
    anthropic_api_key: str = Field(default="", description="Anthropic API key")

    # Google Cloud
    gcp_project: str = Field(default="", description="GCP project ID")
    gcs_audit_bucket: str = Field(
        default="", description="GCS bucket for immutable audit log stream"
    )

    # Connector stub URLs (dev only)
    graph_stub_url: str = Field(
        default="http://localhost:8001", description="MS Graph stub base URL"
    )
    google_stub_url: str = Field(
        default="http://localhost:8002", description="Google API stub base URL"
    )
    fake_gcs_url: str = Field(
        default="http://localhost:4443", description="Fake GCS base URL for dev"
    )

    # Rate limits
    graph_rate_limit_requests_per_10min: int = Field(
        default=10000, description="MS Graph request cap per 10-minute window"
    )
    drive_rate_limit_per_user_qps: int = Field(default=10, description="Drive per-user QPS cap")
    drive_rate_limit_project_qps: int = Field(
        default=1000, description="Drive project-wide QPS cap"
    )
    gadmin_rate_limit_per_user_per_100s: int = Field(
        default=1200, description="Google Admin SDK queries per user per 100s"
    )
    slack_rate_limit_admin_per_min: int = Field(
        default=20, description="Slack admin API requests per minute"
    )
    jumpcloud_rate_limit_per_hour: int = Field(
        default=5000, description="JumpCloud requests per hour"
    )

    # Circuit breaker
    circuit_breaker_trip_errors: int = Field(
        default=5, description="Rate-limit errors in the window before tripping"
    )
    circuit_breaker_window_seconds: int = Field(default=60)
    circuit_breaker_open_seconds: int = Field(default=120)

    @field_validator("env")
    @classmethod
    def validate_env(cls, v: str) -> str:
        allowed = {"dev", "staging", "prod"}
        if v not in allowed:
            raise ValueError(f"env must be one of {allowed}, got {v!r}")
        return v


_settings: Settings | None = None


def get_settings() -> Settings:
    global _settings
    if _settings is None:
        _settings = Settings()  # type: ignore[call-arg]
    return _settings

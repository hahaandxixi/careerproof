from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    app_name: str = "CareerProof API"
    app_env: Literal["development", "test", "production"] = "development"
    debug: bool = True
    api_v1_prefix: str = "/api/v1"
    database_url: str = "postgresql+asyncpg://careerproof:careerproof@127.0.0.1:5432/careerproof"
    jwt_secret: str = "development-only-secret-change-before-production"
    jwt_algorithm: str = "HS256"
    access_token_minutes: int = 30
    refresh_token_days: int = 7
    frontend_origins: list[str] = Field(
        default_factory=lambda: ["http://127.0.0.1:3000", "http://localhost:3000"]
    )
    storage_base_dir: Path = Path("./storage")
    max_archive_bytes: int = 30 * 1024 * 1024
    max_extracted_bytes: int = 100 * 1024 * 1024
    max_file_bytes: int = 1024 * 1024
    max_archive_files: int = 2000
    task_concurrency: int = Field(default=2, ge=1, le=8)
    task_timeout_seconds: float = Field(default=90, gt=0, le=600)
    task_lease_seconds: int = Field(default=120, ge=30, le=3600)
    task_pending_timeout_seconds: int = Field(default=600, ge=60, le=7200)
    task_dispatch_interval_seconds: float = Field(default=2, ge=0.5, le=30)
    max_document_characters: int = Field(default=500_000, ge=1000, le=2_000_000)
    ai_provider: Literal["mock", "bailian", "qianwen", "zhipu"] = "mock"
    ai_external_enabled: bool = False
    dashscope_api_key: SecretStr | None = None
    bailian_base_url: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    bailian_model: str = "qwen-plus"
    bailian_timeout_seconds: float = Field(default=30, gt=0, le=120)
    bailian_max_attempts: int = Field(default=2, ge=1, le=3)
    zhipu_api_key: SecretStr | None = None
    zhipu_base_url: str = "https://open.bigmodel.cn/api/paas/v4"
    zhipu_model: str = "glm-4.7-flash"
    zhipu_timeout_seconds: float = Field(default=90, gt=0, le=120)
    zhipu_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_model_concurrency: int = Field(default=1, ge=1, le=4)
    ai_workflow_timeout_seconds: float = Field(default=180, gt=0, le=240)
    ai_max_requirements: int = Field(default=20, ge=1, le=50)
    ai_local_fallback_enabled: bool = True

    @field_validator("jwt_secret")
    @classmethod
    def reject_weak_production_secret(cls, value: str, info) -> str:
        environment = info.data.get("app_env", "development")
        if environment == "production" and len(value) < 32:
            raise ValueError("JWT_SECRET must contain at least 32 characters in production")
        return value

    @field_validator("storage_base_dir")
    @classmethod
    def resolve_storage_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

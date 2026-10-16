from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import Field, SecretStr, field_validator, model_validator
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
    login_pair_limit: int = Field(default=5, ge=1, le=100)
    login_pair_window_seconds: int = Field(default=300, ge=1, le=3600)
    login_source_limit: int = Field(default=120, ge=1, le=10000)
    login_source_window_seconds: int = Field(default=60, ge=1, le=3600)
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
    ocr_enabled: bool = True
    ocr_max_pages: int = Field(default=10, ge=1, le=50)
    ocr_min_confidence: float = Field(default=0.5, ge=0, le=1)
    ocr_max_image_pixels: int = Field(default=20_000_000, ge=1_000_000, le=50_000_000)
    # Legacy values load old local settings but are refused by the product factory.
    ai_provider: Literal["mock", "bailian", "qianwen", "zhipu", "deepseek"] = "mock"
    ai_external_enabled: bool = False
    # Retained only for historical offline adapter regressions; not product routing.
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
    deepseek_api_key: SecretStr | None = None
    deepseek_base_url: str = "https://api.deepseek.com"
    deepseek_model: str = "deepseek-flash"
    deepseek_timeout_seconds: float = Field(default=90, gt=0, le=120)
    deepseek_max_attempts: int = Field(default=2, ge=1, le=3)
    ai_model_concurrency: int = Field(default=1, ge=1, le=4)
    ai_workflow_timeout_seconds: float = Field(default=180, gt=0, le=240)
    ai_max_requirements: int = Field(default=8, ge=1, le=50)
    ai_max_retrieval_calls: int = Field(default=2, ge=0, le=2)
    ai_per_report_input_token_limit: int = Field(default=12_000, ge=1000, le=100_000)
    ai_per_report_output_token_limit: int = Field(default=4000, ge=200, le=10_000)
    ai_daily_report_limit: int = Field(default=20, ge=1, le=1000)
    ai_daily_input_token_limit: int = Field(default=200_000, ge=1000, le=10_000_000)
    ai_daily_output_token_limit: int = Field(default=40_000, ge=1000, le=2_000_000)
    ai_skip_when_no_evidence: bool = True
    ai_local_fallback_enabled: bool = True
    semantic_retrieval_enabled: bool = True
    semantic_model_cache_dir: Path = Path("./.tmp/models")

    @field_validator("jwt_secret")
    @classmethod
    def reject_weak_production_secret(cls, value: str, info) -> str:
        environment = info.data.get("app_env", "development")
        if environment == "production":
            public_secrets = {
                "development-only-secret-change-before-production",
                "replace-with-at-least-32-random-characters",
            }
            if value.strip() in public_secrets or len(value.strip()) < 32:
                raise ValueError(
                    "JWT_SECRET must be a private secret of at least 32 characters in production; "
                    "development and example secrets are forbidden"
                )
        return value

    @model_validator(mode="after")
    def disable_production_debug(self) -> "Settings":
        if self.app_env == "production":
            self.debug = False
        return self

    @field_validator("storage_base_dir")
    @classmethod
    def resolve_storage_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()

    @field_validator("semantic_model_cache_dir")
    @classmethod
    def resolve_semantic_cache_path(cls, value: Path) -> Path:
        return value.expanduser().resolve()


@lru_cache
def get_settings() -> Settings:
    return Settings()


settings = get_settings()

from typing import List

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        case_sensitive=False,
        extra="ignore",
    )

    # Application
    app_name: str = "汤圆的代码助手"
    app_env: str = "development"
    debug: bool = False
    secret_key: str = "change-me"

    # Database
    database_url: str = "postgresql+asyncpg://tangyuan:tangyuan_dev@localhost:5432/tangyuan_db"
    database_pool_size: int = 20
    database_max_overflow: int = 10

    # Redis
    redis_url: str = "redis://localhost:6379/0"

    # CORS
    cors_origins: List[str] = ["http://localhost:3000"]

    # JWT
    jwt_secret_key: str = "change-me-jwt-secret"
    jwt_algorithm: str = "HS256"
    jwt_access_token_expire_minutes: int = 15
    jwt_refresh_token_expire_days: int = 30

    # Encryption
    fernet_key: str = "change-me-fernet-key"

    # Transport encryption (前端 → 后端敏感字段)
    # PEM 私钥；多 worker 时务必配置同一把，或依赖 uploads/.transport_rsa.pem 共享卷
    transport_rsa_private_key_pem: str = ""
    # production 建议 true：强制敏感字段使用 enc:v1:...
    transport_require_encryption: bool = False

    # Tool Security
    tool_test_timeout_seconds: int = 30
    tool_test_allowed_domains: List[str] = [
        "api.openai.com",
        "api.anthropic.com",
        "generativelanguage.googleapis.com",
    ]
    tool_test_max_response_size: int = 1048576

    # Password
    bcrypt_rounds: int = 12

    # Team
    team_max_members: int = 50
    invite_code_length: int = 6

    # Logging
    log_level: str = "INFO"

    # Knowledge Base
    upload_base_dir: str = "./uploads"
    default_embedding_api_key: str = ""
    default_embedding_base_url: str = "https://api.openai.com/v1"
    default_embedding_model: str = "text-embedding-3-small"
    embedding_batch_size: int = 20
    embedding_request_timeout: int = 60

    # Phase 5: Workflow Execution
    execution_max_concurrent: int = 10
    execution_default_timeout: int = 300
    review_default_timeout: int = 3600


settings = Settings()

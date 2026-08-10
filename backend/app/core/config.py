from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    # Docker 部署时环境变量通过 docker-compose 注入；
    # 本地开发时从 .env 读取（如果存在）
    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # ── Application ──────────────────────────────────────────
    APP_NAME: str = "AI Diagnostic Platform"
    VERSION: str = "0.1.0"
    DEBUG: bool = True
    LOG_LEVEL: str = "INFO"

    # ── Database ─────────────────────────────────────────────
    DATABASE_URL: str = "postgresql://ai:ai@localhost:5432/diagnostic"
    REDIS_URL: str = "redis://localhost:6379/0"
    UPLOAD_DIR: str = "data/raw"

    # ── LLM ─────────────────────────────────────────────────
    LLM_PROVIDER: str = "mock"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ── Milvus (Vector Database) ────────────────────────────
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "knowledge_docs"
    MILVUS_DIM: int = 1536  # embedding dimension (default: OpenAI ada-002)
    MILVUS_ENABLED: bool = False  # 启用 Milvus（未部署时自动回退到关键词搜索）
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # ── Embedding ────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "deepseek"  # 使用 LLM provider 生成 embedding
    EMBEDDING_BATCH_SIZE: int = 32        # 批量嵌入大小

    # ── MinIO (Object Storage) ──────────────────────────────
    MINIO_ENABLED: bool = False
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "diagnostic-logs"
    MINIO_SECURE: bool = False

    # ── Ollama (Local LLM) ──────────────────────────────────
    OLLAMA_ENABLED: bool = False
    OLLAMA_HOST: str = "http://localhost:11434"

    # ── Worker (Celery) ─────────────────────────────────────
    CELERY_BROKER_URL: str = "redis://localhost:6379/1"
    CELERY_RESULT_BACKEND: str = "redis://localhost:6379/2"

    # ── Security ─────────────────────────────────────────────
    SECRET_KEY: str = "CHANGE_ME_IN_PRODUCTION_GENERATE_RANDOM_64_CHAR"
    RATE_LIMIT_ENABLED: bool = False
    RATE_LIMIT_PER_MINUTE: int = 60
    LOG_DESENSITIZE_ENABLED: bool = False

    # ── Monitoring ───────────────────────────────────────────
    PROMETHEUS_METRICS_ENABLED: bool = False

    @field_validator("DEBUG", "MILVUS_ENABLED", "MINIO_ENABLED", "OLLAMA_ENABLED",
                     "MINIO_SECURE", "RATE_LIMIT_ENABLED", "LOG_DESENSITIZE_ENABLED",
                     "PROMETHEUS_METRICS_ENABLED", mode="before")
    @classmethod
    def parse_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("MILVUS_PORT", "MILVUS_DIM", "EMBEDDING_BATCH_SIZE",
                     "RATE_LIMIT_PER_MINUTE", mode="before")
    @classmethod
    def parse_int(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            return int(v.strip())
        return int(v)


settings = Settings()

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
    MAX_UPLOAD_MB: int = 100          # 单文件上传大小上限（MB）
    MAX_PARSE_LINES: int = 200_000    # 解析阶段最多读取行数（防大文件爆内存）
    MAX_ANALYSIS_CHARS: int = 400_000  # 送入分析流水线的最大字符数
    RULES_FILE: str = "data/rules/diagnostic_rules.json"  # 规则持久化文件
    KNOWLEDGE_INDEX_ASYNC: bool = True  # 知识入库后异步同步向量索引（避免保存阻塞）

    # ── LLM ─────────────────────────────────────────────────
    LLM_PROVIDER: str = "mock"
    DEEPSEEK_API_KEY: str = ""
    DEEPSEEK_BASE_URL: str = "https://api.deepseek.com/v1/chat/completions"
    DEEPSEEK_MODEL: str = "deepseek-chat"

    # ── Milvus (Vector Database) ────────────────────────────
    MILVUS_HOST: str = "localhost"
    MILVUS_PORT: int = 19530
    MILVUS_COLLECTION: str = "knowledge_docs"
    MILVUS_DIM: int = 512  # embedding dimension（需与 EMBEDDING 模型维度一致）
    MILVUS_ENABLED: bool = False  # 启用 Milvus（未部署时自动回退到关键词搜索）
    MILVUS_USER: str = ""
    MILVUS_PASSWORD: str = ""

    # ── Embedding ────────────────────────────────────────────
    EMBEDDING_PROVIDER: str = "auto"      # auto | local(BGE) | api | hash
    EMBEDDING_BATCH_SIZE: int = 32        # 批量嵌入大小
    EMBEDDING_API_URL: str = ""           # OpenAI 兼容 /embeddings 端点
    EMBEDDING_API_KEY: str = ""
    EMBEDDING_API_MODEL: str = "text-embedding-3-small"
    EMBEDDING_DIM: int = 512              # 嵌入维度（需与 MILVUS_DIM 一致）
    EMBEDDING_HASH_FALLBACK: bool = True  # 无 BGE/API 时使用确定性哈希嵌入兜底
    EMBEDDING_LOAD_TIMEOUT: float = 30.0  # BGE 模型加载超时（秒），超时回退

    # ── MinIO (Object Storage) ──────────────────────────────
    MINIO_ENABLED: bool = False
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "diagnostic-logs"
    MINIO_SECURE: bool = False

    # ── Knowledge Images（对象存储 + 本地目录回退） ───────────
    KNOWLEDGE_IMAGE_DIR: str = "data/knowledge_images"
    MINIO_KNOWLEDGE_BUCKET: str = "knowledge-images"
    IMAGE_URL_TTL_SECONDS: int = 3600
    MAX_IMAGE_SIZE_MB: int = 10

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
                     "PROMETHEUS_METRICS_ENABLED", "EMBEDDING_HASH_FALLBACK",
                     "KNOWLEDGE_INDEX_ASYNC", mode="before")
    @classmethod
    def parse_bool(cls, v: object) -> bool:
        if isinstance(v, bool):
            return v
        if isinstance(v, str):
            return v.lower() in ("true", "1", "yes", "on")
        return bool(v)

    @field_validator("MILVUS_PORT", "MILVUS_DIM", "EMBEDDING_BATCH_SIZE", "EMBEDDING_DIM",
                     "MAX_UPLOAD_MB", "MAX_PARSE_LINES", "MAX_ANALYSIS_CHARS",
                     "RATE_LIMIT_PER_MINUTE", mode="before")
    @classmethod
    def parse_int(cls, v: object) -> int:
        if isinstance(v, int):
            return v
        if isinstance(v, str):
            return int(v.strip())
        if isinstance(v, float):
            return int(v)
        return int(bool(v))


settings = Settings()

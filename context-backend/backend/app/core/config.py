from pydantic_settings import BaseSettings, SettingsConfigDict
from pydantic import Field

class Settings(BaseSettings):

    # App
    APP_NAME: str
    APP_VERSION: str
    ENVIRONMENT: str
    DEBUG: bool

    # Comma-separated browser origins allowed to call the API directly (CORS).
    # Not needed through the web app's /backend proxy; empty disables CORS.
    CORS_ORIGINS: str = "http://localhost:5173"

    # Database
    DATABASE_URL: str

    POSTGRES_HOST: str
    POSTGRES_PORT: int
    POSTGRES_DATABASE: str
    POSTGRES_USERNAME: str
    POSTGRES_PASSWORD: str

    # Neo4j — not deployed yet (relationship search is unimplemented); optional.
    NEO4J_HOST: str | None = None
    NEO4J_BOLT_PORT: int | None = None
    NEO4J_HTTP_PORT: int | None = None
    NEO4J_USERNAME: str | None = None
    NEO4J_PASSWORD: str | None = None
    NEO4J_URI: str | None = None

    # Redis
    REDIS_HOST: str
    REDIS_PORT: int
    REDIS_DB: int
    REDIS_PASSWORD: str
    REDIS_URL: str

    # RabbitMQ
    RABBITMQ_HOST: str
    RABBITMQ_PORT: int
    RABBITMQ_USERNAME: str
    RABBITMQ_PASSWORD: str
    RABBITMQ_VHOST: str
    RABBITMQ_URL: str

    # Celery
    CELERY_BROKER_URL: str
    CELERY_RESULT_BACKEND: str

    # MinIO
    MINIO_ENDPOINT: str
    MINIO_ACCESS_KEY: str
    MINIO_SECRET_KEY: str
    MINIO_SECURE: bool

    MINIO_QUARANTINE_BUCKET: str
    MINIO_DOCUMENT_BUCKET: str
    MINIO_PARSED_BUCKET: str

    # ChromaDB
    CHROMADB_HOST: str
    CHROMADB_PORT: int
    CHROMADB_SSL: bool

    # Post-security AI verification
    POST_SECURITY_AI_PROVIDER: str = Field(
        validation_alias="post_security_ai_provider",
    )

    POST_SECURITY_AI_BASE_URL: str = Field(
        validation_alias="post_security_ai_base_url",
    )

    POST_SECURITY_AI_MODEL: str = Field(
        validation_alias="post_security_ai_model",
    )

    POST_SECURITY_AI_TIMEOUT_SECONDS: int = Field(
        validation_alias="post_security_ai_timeout_seconds",
    )

    # Ollama — offline LLM generation (Tier B)
    OLLAMA_BASE_URL: str = Field(
        default="http://localhost:11434",
        validation_alias="ollama_base_url",
    )
    OLLAMA_MODEL: str = Field(
        default="qwen3:4b-instruct",
        validation_alias="ollama_model",
    )
    OLLAMA_TIMEOUT_SECONDS: int = Field(
        default=60,
        validation_alias="ollama_timeout_seconds",
    )
    # Ollama's default context window is 2048 tokens and it silently drops the
    # START of a longer prompt (our trusted system instructions). Always set it.
    # On a CPU the prompt is read at ~60 tokens/s, so a smaller window and
    # context (GENERATION_CONTEXT_TOKENS) is what makes answers fast.
    OLLAMA_NUM_CTX: int = Field(default=4096, validation_alias="ollama_num_ctx")
    OLLAMA_NUM_PREDICT: int = Field(default=1024, validation_alias="ollama_num_predict")
    OLLAMA_TEMPERATURE: float = Field(default=0.1, validation_alias="ollama_temperature")
    # Layers offloaded to the GPU. Unset = Ollama decides. 0 = CPU only: use it
    # when the GPU backend (e.g. Vulkan on an integrated GPU) returns garbage
    # such as "prediction aborted, token repeat limit reached".
    OLLAMA_NUM_GPU: int | None = Field(default=None, validation_alias="ollama_num_gpu")
    # How long Ollama keeps the model loaded after a call. Loading it again
    # takes ~20 s on a CPU, so keep it resident.
    OLLAMA_KEEP_ALIVE: str = Field(default="24h", validation_alias="ollama_keep_alive")

    # L11 generation: total wall-clock budget for G5 model calls + G8 repair.
    # Generous on purpose: a slow CPU answer is better than a timeout.
    GENERATION_TIMEOUT_SECONDS: int = Field(default=180, validation_alias="generation_timeout_seconds")
    # Evidence tokens sent to the model (L09). Each 1000 tokens costs ~15 s
    # of prompt reading on a CPU.
    GENERATION_CONTEXT_TOKENS: int = Field(default=1500, validation_alias="generation_context_tokens")
    # G8: a second model call when the answer cites too little. Doubles the
    # answer time, so off by default.
    GENERATION_REPAIR_ENABLED: bool = Field(default=False, validation_alias="generation_repair_enabled")
    # L03: ask the model to refine vague queries before searching. One extra
    # model call per vague query; the deterministic analysis is used otherwise.
    QUERY_ANALYSIS_LLM_ENABLED: bool = Field(default=False, validation_alias="query_analysis_llm_enabled")
    # A question asked right after an upload waits (up to this long) for the
    # project's documents to finish indexing, instead of searching without them.
    RETRIEVAL_INDEXING_WAIT_SECONDS: int = Field(default=420, validation_alias="retrieval_indexing_wait_seconds")

    CHROMADB_HTTP_TIMEOUT_SECONDS: float = Field(
        default=60, validation_alias="chromadb_http_timeout_seconds",
    )

    # Retrieval per-call timeouts (L5)
    RETRIEVAL_EMBED_TIMEOUT_SECONDS: float = Field(
        default=30, validation_alias="retrieval_embed_timeout_seconds",
    )
    RETRIEVAL_VECTOR_TIMEOUT_SECONDS: float = Field(
        default=10, validation_alias="retrieval_vector_timeout_seconds",
    )
    RETRIEVAL_RERANK_TIMEOUT_SECONDS: float = Field(
        default=20, validation_alias="retrieval_rerank_timeout_seconds",
    )
    RETRIEVAL_DB_STATEMENT_TIMEOUT_MS: int = Field(
        default=15000, validation_alias="retrieval_db_statement_timeout_ms",
    )
    # ClamAV
    CLAMAV_HOST: str
    CLAMAV_PORT: int

    # JWT
    JWT_SECRET_KEY: str
    JWT_ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int
    REFRESH_TOKEN_EXPIRE_DAYS: int

    # Email
    MAIL_USERNAME: str
    MAIL_PASSWORD: str
    MAIL_FROM: str
    MAIL_FROM_NAME: str
    MAIL_SERVER: str
    MAIL_PORT: int
    MAIL_STARTTLS: bool
    MAIL_SSL_TLS: bool

    # OTP
    OTP_LENGTH: int
    OTP_EXPIRE_MINUTES: int
    OTP_RESEND_COOLDOWN: int

    # Rate Limit
    MAX_LOGIN_ATTEMPTS: int
    ACCOUNT_LOCK_MINUTES: int

    model_config = SettingsConfigDict(
        env_file=".env",
        extra="ignore",
    )


settings = Settings()
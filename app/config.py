from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    DB_HOST: str
    DB_PORT: int
    DB_NAME: str
    DB_USER: str
    DB_PASSWORD: str

    SECRET_KEY: str
    ALGORITHM: str
    ACCESS_TOKEN_EXPIRE_MINUTES: int

    # Browser origins allowed to call the API (comma separated).
    CORS_ORIGINS: str = (
        "https://satu-survey.vercel.app/",
        "https://n3level.id"
    )

    # MinIO Object Storage
    MINIO_ENDPOINT: str = "localhost:9000"
    MINIO_ACCESS_KEY: str = "minioadmin"
    MINIO_SECRET_KEY: str = "minioadmin"
    MINIO_BUCKET: str = "satusurvey"
    MINIO_SECURE: bool = False

    # Qwen Cloud / LLM (OpenAI-compatible)
    QWEN_API_KEY: str = ""
    QWEN_BASE_URL: str = "https://dashscope.aliyuncs.com/compatible-mode/v1"
    QWEN_MODEL: str = "qwen-plus"

    # LLM token/cost controls
    LLM_CLAIM_EXTRACTION: bool = True
    LLM_EVALUATION: bool = True
    LLM_CLAIM_TEXT_MAX_CHARS: int = 8000
    LLM_MAX_EVIDENCE_PER_CLAIM: int = 12
    LLM_EVIDENCE_EXCERPT_MAX_CHARS: int = 220

    # Upload
    MAX_UPLOAD_SIZE_MB: int = 20

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )


settings = Settings()
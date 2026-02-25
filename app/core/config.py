from pydantic_settings import BaseSettings
from functools import lru_cache
from typing import Literal


class Settings(BaseSettings):
    # ── PostgreSQL ──────────────────────────────────
    postgres_user: str
    postgres_password: str
    postgres_db: str
    postgres_host: str = "postgres"
    postgres_port: int = 5432

    @property
    def database_url(self) -> str:
        return (
            f"postgresql+asyncpg://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    @property
    def database_url_sync(self) -> str:
        """Usada pelo pgvector e scripts de migração"""
        return (
            f"postgresql://{self.postgres_user}:{self.postgres_password}"
            f"@{self.postgres_host}:{self.postgres_port}/{self.postgres_db}"
        )

    # ── Gemini ──────────────────────────────────────
    gemini_api_key: str
    gemini_model: str = "gemini-1.5-pro"
    gemini_embedding_model: str = "models/text-embedding-004"

    # ── LangSmith ───────────────────────────────────
    langchain_tracing_v2: bool = True
    langchain_endpoint: str = "https://api.smith.langchain.com"
    langchain_api_key: str = ""
    langchain_project: str = "vet-clinic-agent"

    # ── WhatsApp ────────────────────────────────────
    whatsapp_provider: Literal["evolution", "meta"] = "evolution"
    evolution_api_url: str = ""
    evolution_api_key: str = ""
    evolution_instance: str = "vet_clinic"
    meta_whatsapp_token: str = ""
    meta_phone_number_id: str = ""
    meta_verify_token: str = ""

    # ── Google APIs ─────────────────────────────────
    google_credentials_json: str = "./credentials/google_credentials.json"
    google_token_json: str = "./credentials/google_token.json"

    # ── SMTP ────────────────────────────────────────
    smtp_host: str = "smtp.gmail.com"
    smtp_port: int = 587
    smtp_user: str = ""
    smtp_password: str = ""

    # ── App ─────────────────────────────────────────
    app_env: Literal["development", "production"] = "development"
    app_secret_key: str = "changeme"
    rag_files_path: str = "/rag_files"

    class Config:
        env_file = ".env"
        env_file_encoding = "utf-8"
        extra = "ignore"


@lru_cache()
def get_settings() -> Settings:
    """
    Singleton — importar assim em qualquer módulo:
    from app.core.config import get_settings
    settings = get_settings()
    """
    return Settings()

"""Deepcast Engine — アプリケーション設定."""

from __future__ import annotations

import os

from pydantic_settings import BaseSettings


class Settings(BaseSettings):
    """Pydantic v2 BaseSettings for Deepcast Engine.

    値は .env ファイルまたは環境変数から読み込まれる。
    """

    # --- Ollama ---
    OLLAMA_BASE_URL: str = "http://localhost:11434"
    OLLAMA_MODEL_GENERATE: str = "qwen2.5"
    OLLAMA_MODEL_EVALUATE: str = "qwen2.5"

    # --- Database ---
    DB_PATH: str = "./data/deepcast.db"

    # --- Quality control ---
    QUALITY_THRESHOLD: int = 80
    MAX_RETRIES: int = 3

    # --- Scheduler ---
    SCHEDULE_INTERVAL_HOURS: int = 1

    # --- API ---
    API_SECRET_KEY: str = "deepcast-dev-secret-change-me"
    CORS_ORIGINS: list[str] = [
        "https://deepcast-ai.com",
        "http://localhost:3000",
        "http://localhost:8001",
    ]

    # --- Voice ---
    TTS_BACKEND: str = "gemini"
    TTS_OUTPUT_DIR: str = "./data/audio"
    GEMINI_API_KEY: str = ""

    # --- Cloudflare R2 ---
    R2_ACCESS_KEY_ID: str = ""
    R2_SECRET_ACCESS_KEY: str = ""
    R2_ENDPOINT: str = ""
    R2_BUCKET: str = "deepcast-audio"
    R2_PUBLIC_URL: str = "https://audio.deepcast-ai.com"

    # --- Publisher ---
    SITE_ROOT: str = os.environ.get("SITE_ROOT", "D:/株式会社　礼/運用中/8_ディープキャスト")
    SITE_URL: str = "https://deepcast-ai.com"
    AUTO_GIT_PUSH: bool = False  # Safety: manual push by default

    # --- Logging ---
    LOG_LEVEL: str = "INFO"

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": True,
    }


settings = Settings()

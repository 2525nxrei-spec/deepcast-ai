"""Deepcast Engine — pytest fixtures."""

from __future__ import annotations

import json
import os
import tempfile
from pathlib import Path
from typing import AsyncGenerator

import pytest
import pytest_asyncio

# ---------------------------------------------------------------------------
# Ensure the engine root is on sys.path so `config.*` / `core.*` resolve.
# ---------------------------------------------------------------------------
import sys

_ENGINE_ROOT = str(Path(__file__).resolve().parents[1])
if _ENGINE_ROOT not in sys.path:
    sys.path.insert(0, _ENGINE_ROOT)

from config.settings import Settings
from core.database import DatabaseManager
from core.llm_client import LLMClient


# ---------------------------------------------------------------------------
# settings — test settings with a temp DB path
# ---------------------------------------------------------------------------


@pytest.fixture()
def settings(tmp_path: Path) -> Settings:
    """Return a Settings instance pointing at a temporary SQLite database."""
    db_path = str(tmp_path / "test_deepcast.db")
    return Settings(
        DB_PATH=db_path,
        API_SECRET_KEY="test-secret-key",
        OLLAMA_BASE_URL="http://localhost:11434",
        OLLAMA_MODEL_GENERATE="llama3",
        OLLAMA_MODEL_EVALUATE="gemma2",
        QUALITY_THRESHOLD=80,
        MAX_RETRIES=3,
    )


# ---------------------------------------------------------------------------
# db_manager — creates a temporary SQLite DB, inits tables, yields, cleans up
# ---------------------------------------------------------------------------


@pytest_asyncio.fixture()
async def db_manager(tmp_path: Path) -> AsyncGenerator[DatabaseManager, None]:
    """Create a DatabaseManager backed by a temporary SQLite file.

    Tables are initialised before yielding. The DB file is cleaned up
    automatically when *tmp_path* goes out of scope.
    """
    db_path = str(tmp_path / "test_deepcast.db")
    manager = DatabaseManager(db_path=db_path)
    await manager.init_db()
    yield manager
    await manager.close()


# ---------------------------------------------------------------------------
# llm_client — creates LLMClient instance
#   NOTE: Requires a running Ollama instance for integration tests.
# ---------------------------------------------------------------------------


@pytest.fixture()
def llm_client() -> LLMClient:
    """Return a fresh LLMClient instance.

    Because LLMClient uses a singleton pattern, we reset it before each test
    so that test isolation is maintained.
    """
    # Reset singleton so each test gets a clean instance
    LLMClient._instance = None
    return LLMClient()


# ---------------------------------------------------------------------------
# sample_content — dict with sample generated content data
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_content() -> dict:
    """Return a sample content dict matching the *contents* table schema."""
    return {
        "title": "AIが変える未来のプログラミング教育",
        "body": "本文テスト " * 600,  # 3000+ chars
        "language": "ja",
        "category": "technology",
        "tags": ["AI", "教育", "プログラミング"],
        "quality_score": 85,
        "status": "draft",
        "topic_source": "research",
        "metadata": {"source": "test", "version": 1},
    }


# ---------------------------------------------------------------------------
# sample_topic — dict with sample topic data
# ---------------------------------------------------------------------------


@pytest.fixture()
def sample_topic() -> dict:
    """Return a sample topic dict matching the *topics* table schema."""
    return {
        "title": "AI時代のキャリア戦略",
        "language": "ja",
        "category": "career",
        "keywords": ["AI", "キャリア", "転職"],
        "priority": 5,
    }


# ---------------------------------------------------------------------------
# prompts_json — temporary prompts.json for ContentGenerator
# ---------------------------------------------------------------------------


@pytest.fixture()
def prompts_json(tmp_path: Path) -> Path:
    """Write a minimal prompts.json to *tmp_path* and return its path."""
    prompts = {
        "topic_research": {
            "ja": "You are a topic researcher. Respond in Japanese.",
            "en": "You are a topic researcher.",
            "default": "You are a topic researcher.",
        },
        "content_generation": {
            "ja": "You are a content writer. Write in Japanese.",
            "en": "You are a content writer.",
            "default": "You are a content writer.",
        },
        "quality_evaluation": {
            "ja": "Evaluate quality of Japanese content.",
            "en": "Evaluate quality of English content.",
            "default": "Evaluate quality.",
        },
    }
    path = tmp_path / "prompts.json"
    path.write_text(json.dumps(prompts, ensure_ascii=False), encoding="utf-8")
    return path

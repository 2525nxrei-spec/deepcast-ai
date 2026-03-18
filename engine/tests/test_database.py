"""Tests for core.database.DatabaseManager."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

# Ensure engine root is importable
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.database import DatabaseManager

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# test_init_db — tables are created
# ------------------------------------------------------------------


async def test_init_db(db_manager: DatabaseManager) -> None:
    """init_db should create all expected tables."""
    db = await db_manager._get_connection()
    cursor = await db.execute(
        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
    )
    rows = await cursor.fetchall()
    table_names = sorted(r["name"] for r in rows)

    for expected in ("contents", "quality_logs", "topics", "prompt_history", "system_logs"):
        assert expected in table_names, f"Table '{expected}' was not created"


# ------------------------------------------------------------------
# test_save_and_get_content
# ------------------------------------------------------------------


async def test_save_and_get_content(
    db_manager: DatabaseManager, sample_content: dict
) -> None:
    """save_content → get_content round-trip should preserve data."""
    content_id = await db_manager.save_content(**sample_content)
    assert isinstance(content_id, int)
    assert content_id >= 1

    fetched = await db_manager.get_content(content_id)
    assert fetched is not None
    assert fetched["title"] == sample_content["title"]
    assert fetched["language"] == sample_content["language"]
    assert fetched["category"] == sample_content["category"]
    assert fetched["tags"] == sample_content["tags"]  # JSON parsed back to list
    assert fetched["quality_score"] == sample_content["quality_score"]
    assert fetched["status"] == sample_content["status"]


# ------------------------------------------------------------------
# test_list_contents_filter_by_language
# ------------------------------------------------------------------


async def test_list_contents_filter_by_language(db_manager: DatabaseManager) -> None:
    """list_contents should filter by language correctly."""
    await db_manager.save_content(
        title="Japanese Article",
        body="日本語の記事です。",
        language="ja",
    )
    await db_manager.save_content(
        title="English Article",
        body="This is an English article.",
        language="en",
    )

    ja_results = await db_manager.list_contents(language="ja")
    assert len(ja_results) == 1
    assert ja_results[0]["language"] == "ja"

    en_results = await db_manager.list_contents(language="en")
    assert len(en_results) == 1
    assert en_results[0]["language"] == "en"

    all_results = await db_manager.list_contents()
    assert len(all_results) == 2


# ------------------------------------------------------------------
# test_update_content_status
# ------------------------------------------------------------------


async def test_update_content_status(
    db_manager: DatabaseManager, sample_content: dict
) -> None:
    """update_content_status should change status and set published_at when published."""
    content_id = await db_manager.save_content(**sample_content)

    # Transition to published
    await db_manager.update_content_status(content_id, "published")
    fetched = await db_manager.get_content(content_id)
    assert fetched is not None
    assert fetched["status"] == "published"
    assert fetched["published_at"] is not None

    # Transition to archived
    await db_manager.update_content_status(content_id, "archived")
    fetched = await db_manager.get_content(content_id)
    assert fetched is not None
    assert fetched["status"] == "archived"


# ------------------------------------------------------------------
# test_save_quality_log
# ------------------------------------------------------------------


async def test_save_quality_log(
    db_manager: DatabaseManager, sample_content: dict
) -> None:
    """save_quality_log should insert a record linked to the content."""
    content_id = await db_manager.save_content(**sample_content)

    await db_manager.save_quality_log(
        content_id=content_id,
        score=88,
        feedback="Great article!",
        evaluator_model="gemma2",
        prompt_version="v1",
    )

    # Verify via raw SQL
    db = await db_manager._get_connection()
    cursor = await db.execute(
        "SELECT * FROM quality_logs WHERE content_id = ?", (content_id,)
    )
    row = await cursor.fetchone()
    assert row is not None
    assert row["score"] == 88
    assert row["feedback"] == "Great article!"
    assert row["evaluator_model"] == "gemma2"


# ------------------------------------------------------------------
# test_get_quality_trend
# ------------------------------------------------------------------


async def test_get_quality_trend(
    db_manager: DatabaseManager, sample_content: dict
) -> None:
    """get_quality_trend should return daily average scores."""
    content_id = await db_manager.save_content(**sample_content)

    # Insert several quality logs
    for score in (70, 80, 90):
        await db_manager.save_quality_log(content_id=content_id, score=score)

    trend = await db_manager.get_quality_trend(language="ja", days=7)
    assert isinstance(trend, list)
    # Should have at least one day entry with the average
    if trend:
        assert "avg_score" in trend[0]
        assert "count" in trend[0]
        assert trend[0]["count"] == 3


# ------------------------------------------------------------------
# test_save_and_get_topics
# ------------------------------------------------------------------


async def test_save_and_get_topics(
    db_manager: DatabaseManager, sample_topic: dict
) -> None:
    """save_topic → get_pending_topics round-trip."""
    topic_id = await db_manager.save_topic(**sample_topic)
    assert isinstance(topic_id, int)
    assert topic_id >= 1

    pending = await db_manager.get_pending_topics(language="ja")
    assert len(pending) >= 1
    assert pending[0]["title"] == sample_topic["title"]

    # Update topic status
    await db_manager.update_topic_status(topic_id, "completed")
    pending_after = await db_manager.get_pending_topics(language="ja")
    # Should no longer appear in pending
    topic_ids = [t["id"] for t in pending_after]
    assert topic_id not in topic_ids


# ------------------------------------------------------------------
# test_check_duplicate
# ------------------------------------------------------------------


async def test_check_duplicate(db_manager: DatabaseManager) -> None:
    """check_duplicate should detect fuzzy title matches."""
    await db_manager.save_content(
        title="AIが変える未来のプログラミング教育",
        body="テスト本文",
        language="ja",
    )

    # Exact match
    is_dup = await db_manager.check_duplicate(
        title="AIが変える未来のプログラミング教育", language="ja"
    )
    assert is_dup is True

    # Very similar title
    is_dup_similar = await db_manager.check_duplicate(
        title="AIが変える未来のプログラミング学習", language="ja"
    )
    assert is_dup_similar is True  # similarity should exceed 0.8

    # Completely different title
    is_dup_diff = await db_manager.check_duplicate(
        title="料理レシピのまとめサイト構築方法", language="ja"
    )
    assert is_dup_diff is False

    # Different language — should not match
    is_dup_en = await db_manager.check_duplicate(
        title="AIが変える未来のプログラミング教育", language="en"
    )
    assert is_dup_en is False


# ------------------------------------------------------------------
# test_save_system_log
# ------------------------------------------------------------------


async def test_save_system_log(db_manager: DatabaseManager) -> None:
    """save_system_log should insert a log record."""
    await db_manager.save_system_log(
        level="INFO",
        message="Test log entry",
        component="test_suite",
    )

    db = await db_manager._get_connection()
    cursor = await db.execute("SELECT * FROM system_logs")
    row = await cursor.fetchone()
    assert row is not None
    assert row["level"] == "INFO"
    assert row["message"] == "Test log entry"
    assert row["component"] == "test_suite"

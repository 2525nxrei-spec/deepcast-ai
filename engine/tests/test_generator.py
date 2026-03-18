"""Tests for engine.generator.ContentGenerator with mocked LLM."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.generator import ContentGenerator, GeneratedContent, TopicIdea

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _make_topic(**overrides) -> TopicIdea:
    """Create a TopicIdea with sensible defaults."""
    defaults = {
        "title": "AIが変える未来のプログラミング教育",
        "category": "technology",
        "keywords": ["AI", "教育", "プログラミング"],
        "target_audience": "エンジニア志望者",
        "angle": "教育現場でのAI活用事例",
    }
    defaults.update(overrides)
    return TopicIdea(**defaults)


def _make_content_json(language: str = "ja", body_length: int = 3500) -> str:
    """Return a JSON string for a valid GeneratedContent."""
    body = "テスト記事 " * (body_length // 5) if language == "ja" else "Test body. " * (body_length // 11)
    data = {
        "title": "テスト記事タイトル" if language == "ja" else "Test Article Title",
        "body": body,
        "summary": "要約テスト" if language == "ja" else "Test summary",
        "tags": ["tag1", "tag2"],
        "category": "technology",
        "seo_keywords": ["AI", "教育"],
        "estimated_read_time": 5,
    }
    return json.dumps(data, ensure_ascii=False)


def _make_topic_list_json(count: int = 3) -> str:
    """Return a JSON string for a list of topic ideas."""
    topics = [
        {
            "title": f"Topic {i}",
            "category": "technology",
            "keywords": ["kw1", "kw2"],
            "target_audience": "developers",
            "angle": f"Unique angle {i}",
        }
        for i in range(count)
    ]
    return json.dumps(topics, ensure_ascii=False)


def _build_generator(
    llm_mock: AsyncMock,
    prompts_json: Path,
) -> ContentGenerator:
    """Instantiate ContentGenerator with a mocked LLM and mock DB."""
    db_mock = AsyncMock()
    db_mock.topic_exists = AsyncMock(return_value=False)
    db_mock.save_topic = AsyncMock(return_value=1)
    db_mock.save_content = AsyncMock(return_value=1)
    db_mock.save_quality_log = AsyncMock()

    generator = ContentGenerator(
        llm_client=llm_mock,
        db=db_mock,
        prompts_path=str(prompts_json),
    )
    return generator


# ------------------------------------------------------------------
# test_research_topics — mock LLM to return topic JSON
# ------------------------------------------------------------------


async def test_research_topics(prompts_json: Path) -> None:
    """research_topics should parse LLM output into TopicIdea list."""
    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=_make_topic_list_json(5))

    gen = _build_generator(llm_mock, prompts_json)
    topics = await gen.research_topics(language="ja", count=5)

    assert isinstance(topics, list)
    assert len(topics) <= 5
    for t in topics:
        assert isinstance(t, TopicIdea)
        assert t.title
        assert t.category

    # LLM should have been called once
    llm_mock.generate.assert_called_once()


# ------------------------------------------------------------------
# test_generate_content_ja — verify 3000+ char requirement
# ------------------------------------------------------------------


async def test_generate_content_ja(prompts_json: Path) -> None:
    """generate_content for 'ja' should return content with 3000+ chars in body."""
    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=_make_content_json("ja", 3500))

    gen = _build_generator(llm_mock, prompts_json)
    topic = _make_topic()

    content = await gen.generate_content(topic, language="ja")

    assert isinstance(content, GeneratedContent)
    assert len(content.body) >= 3000, (
        f"Japanese content body should be >= 3000 chars, got {len(content.body)}"
    )
    assert content.title
    assert content.tags
    assert content.estimated_read_time > 0


# ------------------------------------------------------------------
# test_generate_content_en — verify structure
# ------------------------------------------------------------------


async def test_generate_content_en(prompts_json: Path) -> None:
    """generate_content for 'en' should return properly structured content."""
    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=_make_content_json("en", 2000))

    gen = _build_generator(llm_mock, prompts_json)
    topic = _make_topic(
        title="Future of AI in Education",
        target_audience="Developers",
        angle="Practical applications",
    )

    content = await gen.generate_content(topic, language="en")

    assert isinstance(content, GeneratedContent)
    assert content.title
    assert content.body
    assert content.summary
    assert isinstance(content.tags, list)
    assert isinstance(content.seo_keywords, list)
    assert isinstance(content.estimated_read_time, int)


# ------------------------------------------------------------------
# test_pydantic_validation — invalid LLM output triggers retry
# ------------------------------------------------------------------


async def test_pydantic_validation(prompts_json: Path) -> None:
    """When LLM returns invalid JSON, generator should retry then raise ValueError."""
    # First two calls return invalid JSON, third also invalid → should raise
    invalid_json = '{"title": "No body field"}'  # missing required fields
    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=invalid_json)

    gen = _build_generator(llm_mock, prompts_json)
    gen.max_retries = 3
    topic = _make_topic()

    with pytest.raises(ValueError, match="Content generation failed after 3 attempts"):
        await gen.generate_content(topic, language="ja")

    # Should have been called max_retries times
    assert llm_mock.generate.call_count == 3

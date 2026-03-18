"""Tests for engine.trend_analyzer — TrendAnalyzer with mocked LLM."""

from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------

_CURRENT_MONTH = datetime.now(timezone.utc).month

_SEASON_MAP = {
    12: "winter", 1: "winter", 2: "winter",
    3: "spring", 4: "spring", 5: "spring",
    6: "summer", 7: "summer", 8: "summer",
    9: "autumn", 10: "autumn", 11: "autumn",
}

CURRENT_SEASON = _SEASON_MAP[_CURRENT_MONTH]


def _mock_db_with_content(contents: list[dict]) -> AsyncMock:
    """Return a DB mock that returns the given content rows."""
    db_mock = AsyncMock()
    db_mock.fetch_all = AsyncMock(return_value=contents)
    db_mock.list_contents = AsyncMock(return_value=contents)
    return db_mock


# ------------------------------------------------------------------
# test_analyze_content_gaps
# ------------------------------------------------------------------


async def test_analyze_content_gaps() -> None:
    """Mock DB data and verify gap detection identifies missing categories."""
    from engine.trend_analyzer import TrendAnalyzer

    # Existing content covers "technology" and "career" — "health" is a gap
    existing_contents = [
        {"category": "technology", "title": "AI入門", "language": "ja", "tags": '["AI"]'},
        {"category": "technology", "title": "Python基礎", "language": "ja", "tags": '["Python"]'},
        {"category": "career", "title": "転職ガイド", "language": "ja", "tags": '["転職"]'},
    ]
    db_mock = _mock_db_with_content(existing_contents)

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(
        return_value={
            "gaps": [
                {
                    "category": "health",
                    "reason": "健康関連のコンテンツがない",
                    "suggested_topics": ["AI×ヘルスケア", "メンタルヘルス"],
                },
                {
                    "category": "finance",
                    "reason": "金融関連のコンテンツがない",
                    "suggested_topics": ["AI投資", "フィンテック入門"],
                },
            ]
        }
    )

    analyzer = TrendAnalyzer(llm=llm_mock, db=db_mock)

    gaps = await analyzer.analyze_content_gaps(language="ja")

    assert isinstance(gaps, list)
    assert len(gaps) >= 1
    gap_categories = [g["category"] for g in gaps]
    # The mocked LLM identifies health and finance as gaps
    assert "health" in gap_categories or "finance" in gap_categories


# ------------------------------------------------------------------
# test_predict_topics
# ------------------------------------------------------------------


async def test_predict_topics() -> None:
    """Mock LLM JSON output and verify TrendSignal validation."""
    from engine.trend_analyzer import TrendAnalyzer, TrendSignal

    llm_response = {
        "trends": [
            {
                "topic": "生成AIの企業活用",
                "confidence": 0.85,
                "category": "technology",
                "keywords": ["生成AI", "企業", "DX"],
                "reasoning": "企業でのAI導入が加速中",
            },
            {
                "topic": "リモートワーク最新事情",
                "confidence": 0.72,
                "category": "career",
                "keywords": ["リモートワーク", "働き方"],
                "reasoning": "ハイブリッドワークが定着",
            },
        ]
    }

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=llm_response)

    db_mock = _mock_db_with_content([])
    analyzer = TrendAnalyzer(llm=llm_mock, db=db_mock)

    signals = await analyzer.predict_topics(language="ja", count=5)

    assert isinstance(signals, list)
    assert len(signals) == 2
    for signal in signals:
        assert isinstance(signal, TrendSignal)
        assert signal.topic
        assert 0.0 <= signal.confidence <= 1.0
        assert signal.category
        assert isinstance(signal.keywords, list)

    llm_mock.generate_json.assert_called_once()


# ------------------------------------------------------------------
# test_content_calendar
# ------------------------------------------------------------------


async def test_content_calendar() -> None:
    """Verify calendar generation produces entries for 7 days."""
    from engine.trend_analyzer import TrendAnalyzer

    # LLM returns a calendar with 7 days of content
    calendar_response = {
        "calendar": [
            {
                "day": i + 1,
                "date": f"2026-03-{17 + i:02d}",
                "topic": f"トピック {i + 1}",
                "category": "technology",
                "language": "ja",
            }
            for i in range(7)
        ]
    }

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=calendar_response)

    db_mock = _mock_db_with_content([])
    analyzer = TrendAnalyzer(llm=llm_mock, db=db_mock)

    calendar = await analyzer.generate_content_calendar(
        language="ja",
        days=7,
    )

    assert isinstance(calendar, list)
    assert len(calendar) == 7, f"Calendar should have 7 entries, got {len(calendar)}"

    for entry in calendar:
        assert "topic" in entry
        assert "date" in entry or "day" in entry
        assert entry["topic"]


async def test_content_calendar_no_duplicates() -> None:
    """Calendar entries should have distinct topics."""
    from engine.trend_analyzer import TrendAnalyzer

    calendar_response = {
        "calendar": [
            {
                "day": i + 1,
                "date": f"2026-03-{17 + i:02d}",
                "topic": f"ユニークトピック {i + 1}",
                "category": "technology",
                "language": "ja",
            }
            for i in range(7)
        ]
    }

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=calendar_response)

    db_mock = _mock_db_with_content([])
    analyzer = TrendAnalyzer(llm=llm_mock, db=db_mock)

    calendar = await analyzer.generate_content_calendar(language="ja", days=7)

    topics = [e["topic"] for e in calendar]
    assert len(topics) == len(set(topics)), "Calendar should not have duplicate topics"


# ------------------------------------------------------------------
# test_seasonal_themes
# ------------------------------------------------------------------


async def test_seasonal_themes() -> None:
    """Verify themes include the current season."""
    from engine.trend_analyzer import TrendAnalyzer

    themes_response = {
        "themes": [
            {
                "theme": f"{CURRENT_SEASON}に読みたいAI記事",
                "season": CURRENT_SEASON,
                "topics": ["季節のAI活用", "旬のテック"],
            },
            {
                "theme": "年間を通じたキャリア戦略",
                "season": "all",
                "topics": ["キャリアプランニング"],
            },
        ]
    }

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=themes_response)

    db_mock = _mock_db_with_content([])
    analyzer = TrendAnalyzer(llm=llm_mock, db=db_mock)

    themes = await analyzer.get_seasonal_themes(language="ja")

    assert isinstance(themes, list)
    assert len(themes) >= 1

    # At least one theme should reference the current season
    season_values = [t.get("season", "") for t in themes]
    assert CURRENT_SEASON in season_values or "all" in season_values, (
        f"Themes should include current season '{CURRENT_SEASON}', "
        f"got seasons: {season_values}"
    )

    # Each theme should have topics
    for theme in themes:
        assert "theme" in theme
        assert "topics" in theme
        assert isinstance(theme["topics"], list)

"""Tests for engine.evaluator.ContentEvaluator with mocked LLM."""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import AsyncMock

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from engine.evaluator import ContentEvaluator, EvaluationResult

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# Helpers
# ------------------------------------------------------------------


def _valid_evaluation_json(**overrides) -> str:
    """Return a valid EvaluationResult JSON string."""
    data = {
        "overall_score": 85,
        "naturalness": 80,
        "engagement": 90,
        "seo_quality": 85,
        "structure": 88,
        "originality": 82,
        "feedback": "Well-written article with good structure.",
        "suggestions": ["Add more examples", "Improve SEO keywords"],
    }
    data.update(overrides)
    return json.dumps(data, ensure_ascii=False)


def _low_score_evaluation_json() -> str:
    """Return an evaluation JSON with a low score."""
    return _valid_evaluation_json(
        overall_score=35,
        naturalness=30,
        engagement=40,
        seo_quality=30,
        structure=35,
        originality=40,
        feedback="Content lacks depth and has unnatural phrasing.",
        suggestions=["Rewrite with more detail", "Use more natural language", "Add data"],
    )


def _build_evaluator(llm_mock: AsyncMock) -> ContentEvaluator:
    """Create a ContentEvaluator with mocked dependencies."""
    db_mock = AsyncMock()
    evaluator = ContentEvaluator(llm=llm_mock, db=db_mock)
    return evaluator


# ------------------------------------------------------------------
# test_evaluate_content
# ------------------------------------------------------------------


async def test_evaluate_content() -> None:
    """evaluate should return an EvaluationResult with correct scores."""
    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=_valid_evaluation_json())

    evaluator = _build_evaluator(llm_mock)
    result = await evaluator.evaluate(
        content_title="Test Article",
        content_body="This is the test body of the article.",
        language="en",
    )

    assert isinstance(result, EvaluationResult)
    assert result.overall_score == 85
    assert result.naturalness == 80
    assert result.engagement == 90
    assert result.seo_quality == 85
    assert result.structure == 88
    assert result.originality == 82
    assert isinstance(result.feedback, str)
    assert isinstance(result.suggestions, list)
    assert len(result.suggestions) > 0

    llm_mock.generate.assert_called_once()


# ------------------------------------------------------------------
# test_evaluate_low_score
# ------------------------------------------------------------------


async def test_evaluate_low_score() -> None:
    """evaluate should correctly return low scores without fallback."""
    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=_low_score_evaluation_json())

    evaluator = _build_evaluator(llm_mock)
    result = await evaluator.evaluate(
        content_title="Low Quality Article",
        content_body="Short body.",
        language="ja",
    )

    assert isinstance(result, EvaluationResult)
    assert result.overall_score == 35
    assert result.naturalness == 30
    assert result.feedback == "Content lacks depth and has unnatural phrasing."


# ------------------------------------------------------------------
# test_evaluate_json_parse_failure_retry
# ------------------------------------------------------------------


async def test_evaluate_json_parse_failure_retry() -> None:
    """When LLM returns invalid JSON, evaluator retries then falls back."""
    invalid_response = "This is not JSON at all, sorry!"
    valid_response = _valid_evaluation_json(overall_score=72)

    llm_mock = AsyncMock()
    # First two calls fail, third succeeds
    llm_mock.generate = AsyncMock(
        side_effect=[invalid_response, invalid_response, valid_response]
    )

    evaluator = _build_evaluator(llm_mock)
    evaluator._max_retries = 3

    result = await evaluator.evaluate(
        content_title="Retry Test",
        content_body="Body for retry testing.",
        language="en",
    )

    assert isinstance(result, EvaluationResult)
    assert result.overall_score == 72
    assert llm_mock.generate.call_count == 3


async def test_evaluate_all_retries_fail_returns_fallback() -> None:
    """When all retries fail, evaluator returns fallback score of 50."""
    invalid_response = "NOT VALID JSON"

    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(return_value=invalid_response)

    evaluator = _build_evaluator(llm_mock)
    evaluator._max_retries = 3

    result = await evaluator.evaluate(
        content_title="All Fail",
        content_body="This should trigger fallback.",
        language="ja",
    )

    assert isinstance(result, EvaluationResult)
    assert result.overall_score == 50  # fallback
    assert "fallback" in result.feedback.lower()
    assert llm_mock.generate.call_count == 3


# ------------------------------------------------------------------
# test_quality_trend
# ------------------------------------------------------------------


async def test_quality_trend() -> None:
    """get_quality_trend should return trend data from the database."""
    llm_mock = AsyncMock()

    db_mock = AsyncMock()
    # Simulate fetch_all returning scored rows
    db_mock.fetch_all = AsyncMock(
        return_value=[
            {"overall_score": 70, "evaluated_at": "2025-01-01T00:00:00Z"},
            {"overall_score": 75, "evaluated_at": "2025-01-02T00:00:00Z"},
            {"overall_score": 80, "evaluated_at": "2025-01-03T00:00:00Z"},
            {"overall_score": 85, "evaluated_at": "2025-01-04T00:00:00Z"},
        ]
    )

    evaluator = ContentEvaluator(llm=llm_mock, db=db_mock)
    trend = await evaluator.get_quality_trend(language="ja", days=7)

    assert isinstance(trend, dict)
    assert "avg_score" in trend
    assert "trend" in trend
    assert "total_evaluated" in trend
    assert trend["total_evaluated"] == 4
    assert trend["avg_score"] == pytest.approx(77.5, rel=0.01)
    assert trend["trend"] == "improving"  # second half avg > first half avg + 5


async def test_quality_trend_empty() -> None:
    """get_quality_trend with no data should return stable / zero."""
    llm_mock = AsyncMock()
    db_mock = AsyncMock()
    db_mock.fetch_all = AsyncMock(return_value=[])

    evaluator = ContentEvaluator(llm=llm_mock, db=db_mock)
    trend = await evaluator.get_quality_trend(language="en", days=7)

    assert trend["avg_score"] == 0.0
    assert trend["trend"] == "stable"
    assert trend["total_evaluated"] == 0

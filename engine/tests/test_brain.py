"""Tests for engine.brain — Brain multi-agent pipeline."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# Helpers — lightweight stand-ins for Brain data classes
# ------------------------------------------------------------------


def _make_agent_task(**overrides) -> dict:
    """Return a dict representing an AgentTask."""
    defaults = {
        "task_id": "task-001",
        "task_type": "create",
        "topic": "AIが変える未来のプログラミング教育",
        "language": "ja",
        "parameters": {},
        "status": "pending",
    }
    defaults.update(overrides)
    return defaults


def _make_content_output(**overrides) -> dict:
    """Return a dict representing content produced by the creator agent."""
    defaults = {
        "title": "AIが変える未来のプログラミング教育",
        "body": "テスト記事 " * 700,
        "summary": "AIと教育に関する解説記事",
        "tags": ["AI", "教育"],
        "category": "technology",
        "quality_score": 85,
    }
    defaults.update(overrides)
    return defaults


def _make_edited_output(**overrides) -> dict:
    """Return a dict representing content after the editor agent."""
    base = _make_content_output()
    base.update(
        {
            "sns_summary_twitter": "AIが変える教育の未来 #AI #教育",
            "sns_summary_instagram": "AIと教育の最前線をお届け",
            "faq": [
                {"q": "AIは教育にどう影響しますか？", "a": "個別最適化学習が可能になります。"}
            ],
        }
    )
    base.update(overrides)
    return base


# ------------------------------------------------------------------
# test_plan_generates_tasks
# ------------------------------------------------------------------


async def test_plan_generates_tasks() -> None:
    """Planner agent should produce a list of AgentTasks from a topic."""
    from engine.brain import Brain, AgentTask

    llm_mock = AsyncMock()
    # Planner returns a JSON list of tasks
    llm_mock.generate_json = AsyncMock(
        return_value={
            "tasks": [
                {
                    "task_id": "t1",
                    "task_type": "research",
                    "topic": "AI教育",
                    "language": "ja",
                    "parameters": {},
                },
                {
                    "task_id": "t2",
                    "task_type": "create",
                    "topic": "AI教育",
                    "language": "ja",
                    "parameters": {},
                },
            ]
        }
    )

    db_mock = AsyncMock()
    brain = Brain(llm=llm_mock, db=db_mock)

    tasks = await brain.plan(topic="AI教育", language="ja")

    assert isinstance(tasks, list)
    assert len(tasks) >= 1
    for task in tasks:
        assert isinstance(task, AgentTask)
        assert task.task_type in ("research", "create", "edit", "publish")
    llm_mock.generate_json.assert_called_once()


# ------------------------------------------------------------------
# test_create_produces_content
# ------------------------------------------------------------------


async def test_create_produces_content() -> None:
    """Creator agent should fill output_data with title, body, tags, etc."""
    from engine.brain import Brain, AgentTask

    llm_mock = AsyncMock()
    llm_mock.generate = AsyncMock(
        return_value="テスト記事 " * 700
    )
    llm_mock.generate_json = AsyncMock(
        return_value=_make_content_output()
    )

    db_mock = AsyncMock()
    brain = Brain(llm=llm_mock, db=db_mock)

    task = AgentTask(
        task_id="t-create",
        task_type="create",
        topic="AI教育",
        language="ja",
        parameters={},
    )

    result = await brain.create(task)

    assert result.output_data is not None
    assert "title" in result.output_data
    assert "body" in result.output_data
    assert len(result.output_data["body"]) > 0
    assert result.status == "completed"


# ------------------------------------------------------------------
# test_edit_adds_metadata
# ------------------------------------------------------------------


async def test_edit_adds_metadata() -> None:
    """Editor agent should add SNS summaries and FAQ to content."""
    from engine.brain import Brain, AgentTask

    content = _make_content_output()
    edited = _make_edited_output()

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=edited)

    db_mock = AsyncMock()
    brain = Brain(llm=llm_mock, db=db_mock)

    task = AgentTask(
        task_id="t-edit",
        task_type="edit",
        topic="AI教育",
        language="ja",
        parameters={},
    )
    task.input_data = content

    result = await brain.edit(task)

    assert result.output_data is not None
    assert "sns_summary_twitter" in result.output_data
    assert "sns_summary_instagram" in result.output_data
    assert "faq" in result.output_data
    assert isinstance(result.output_data["faq"], list)
    assert len(result.output_data["faq"]) >= 1


# ------------------------------------------------------------------
# test_full_pipeline
# ------------------------------------------------------------------


async def test_full_pipeline() -> None:
    """Full pipeline: plan -> create -> edit -> publish should complete."""
    from engine.brain import Brain, AgentTask

    plan_result = {
        "tasks": [
            {
                "task_id": "t1",
                "task_type": "create",
                "topic": "AI教育",
                "language": "ja",
                "parameters": {},
            },
            {
                "task_id": "t2",
                "task_type": "edit",
                "topic": "AI教育",
                "language": "ja",
                "parameters": {},
            },
            {
                "task_id": "t3",
                "task_type": "publish",
                "topic": "AI教育",
                "language": "ja",
                "parameters": {},
            },
        ]
    }
    content = _make_content_output()
    edited = _make_edited_output()

    llm_mock = AsyncMock()
    # plan call
    llm_mock.generate_json = AsyncMock(
        side_effect=[plan_result, content, edited]
    )
    llm_mock.generate = AsyncMock(return_value="dummy")

    db_mock = AsyncMock()
    db_mock.save_content = AsyncMock(return_value=42)
    db_mock.save_quality_log = AsyncMock()

    brain = Brain(llm=llm_mock, db=db_mock)

    result = await brain.run_pipeline(topic="AI教育", language="ja")

    assert result["status"] == "published"
    assert result["content_id"] is not None
    # DB save should have been called
    db_mock.save_content.assert_called_once()


# ------------------------------------------------------------------
# test_pipeline_handles_low_quality
# ------------------------------------------------------------------


async def test_pipeline_handles_low_quality() -> None:
    """Pipeline should re-edit content when quality score is below threshold."""
    from engine.brain import Brain, AgentTask

    low_quality_content = _make_content_output(quality_score=45)
    high_quality_content = _make_content_output(quality_score=90)

    plan_result = {
        "tasks": [
            {
                "task_id": "t1",
                "task_type": "create",
                "topic": "AI教育",
                "language": "ja",
                "parameters": {},
            },
        ]
    }

    llm_mock = AsyncMock()
    # First create returns low quality, second returns high quality
    llm_mock.generate_json = AsyncMock(
        side_effect=[
            plan_result,
            low_quality_content,
            _make_edited_output(quality_score=45),
            high_quality_content,
            _make_edited_output(quality_score=90),
        ]
    )
    llm_mock.generate = AsyncMock(return_value="dummy")

    db_mock = AsyncMock()
    db_mock.save_content = AsyncMock(return_value=42)
    db_mock.save_quality_log = AsyncMock()

    brain = Brain(llm=llm_mock, db=db_mock, quality_threshold=80)

    result = await brain.run_pipeline(topic="AI教育", language="ja")

    # Should have retried due to low quality
    assert llm_mock.generate_json.call_count >= 3
    assert result["status"] in ("published", "re-edited")

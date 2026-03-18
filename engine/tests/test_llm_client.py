"""Tests for core.llm_client.LLMClient.

All tests are marked as integration tests because they require
a running Ollama instance.  Run with:

    pytest -m integration tests/test_llm_client.py
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from core.llm_client import LLMClient

pytestmark = [pytest.mark.asyncio, pytest.mark.integration]


# ------------------------------------------------------------------
# Fixture: reset the singleton between tests
# ------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _reset_singleton():
    """Ensure each test gets a fresh LLMClient instance."""
    LLMClient._instance = None
    yield
    LLMClient._instance = None


# ------------------------------------------------------------------
# test_health_check
# ------------------------------------------------------------------


async def test_health_check() -> None:
    """check_health should return True when Ollama is running."""
    client = LLMClient()
    try:
        healthy = await client.check_health()
        assert isinstance(healthy, bool)
        # If Ollama is running, this should be True
        assert healthy is True
    finally:
        await client.close()


# ------------------------------------------------------------------
# test_generate_text
# ------------------------------------------------------------------


async def test_generate_text() -> None:
    """generate should return a non-empty string."""
    client = LLMClient()
    try:
        result = await client.generate(
            prompt="Say hello in one sentence.",
            system_prompt="You are a helpful assistant.",
        )
        assert isinstance(result, str)
        assert len(result) > 0
    finally:
        await client.close()


# ------------------------------------------------------------------
# test_generate_json
# ------------------------------------------------------------------


async def test_generate_json() -> None:
    """generate_json should return a parsed dict."""
    client = LLMClient()
    try:
        result = await client.generate_json(
            prompt='Return a JSON object with keys "name" and "value". Example: {"name": "test", "value": 42}',
            system_prompt="You are a helpful assistant that always responds with valid JSON.",
        )
        assert isinstance(result, dict)
    finally:
        await client.close()


# ------------------------------------------------------------------
# test_list_models
# ------------------------------------------------------------------


async def test_list_models() -> None:
    """list_models should return a list of model name strings."""
    client = LLMClient()
    try:
        models = await client.list_models()
        assert isinstance(models, list)
        # At least one model should be installed
        assert len(models) > 0
        assert all(isinstance(m, str) for m in models)
    finally:
        await client.close()

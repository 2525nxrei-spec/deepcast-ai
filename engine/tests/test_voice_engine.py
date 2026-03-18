"""Tests for engine.voice_engine — VoiceEngine TTS and podcast script generation."""

from __future__ import annotations

import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# test_check_backends
# ------------------------------------------------------------------


async def test_check_backends() -> None:
    """VoiceEngine.check_backends should return a dict of available backends."""
    from engine.voice_engine import VoiceEngine

    llm_mock = AsyncMock()
    engine = VoiceEngine(llm=llm_mock)

    backends = await engine.check_backends()

    assert isinstance(backends, dict)
    # Should have at least edge_tts as a key (may or may not be available)
    assert "edge_tts" in backends
    # Each value should be a bool indicating availability
    for name, available in backends.items():
        assert isinstance(name, str)
        assert isinstance(available, bool)


# ------------------------------------------------------------------
# test_text_splitting
# ------------------------------------------------------------------


async def test_text_splitting() -> None:
    """Long text should be split at sentence boundaries."""
    from engine.voice_engine import VoiceEngine

    llm_mock = AsyncMock()
    engine = VoiceEngine(llm=llm_mock)

    # Build a long text with clear sentence boundaries
    sentences = [
        "これは最初の文です。",
        "二番目の文が続きます。",
        "三番目の文はここにあります。",
        "四番目の文で段落が終わります。",
        "五番目の文は新しい段落です。",
    ]
    long_text = "".join(sentences)

    chunks = engine.split_text(long_text, max_chars=50)

    assert isinstance(chunks, list)
    assert len(chunks) >= 2, "Long text should be split into multiple chunks"

    # Verify no chunk exceeds the max length (with some tolerance for sentence boundaries)
    for chunk in chunks:
        assert len(chunk) <= 80, (
            f"Chunk too long ({len(chunk)} chars): {chunk[:40]}..."
        )

    # Verify all text is preserved when joined
    joined = "".join(chunks)
    assert joined == long_text, "Splitting should preserve all text"


async def test_text_splitting_short_text() -> None:
    """Short text should remain as a single chunk."""
    from engine.voice_engine import VoiceEngine

    llm_mock = AsyncMock()
    engine = VoiceEngine(llm=llm_mock)

    short_text = "短いテキストです。"
    chunks = engine.split_text(short_text, max_chars=500)

    assert len(chunks) == 1
    assert chunks[0] == short_text


# ------------------------------------------------------------------
# test_synthesize_edge — integration test (requires edge-tts)
# ------------------------------------------------------------------


@pytest.mark.integration
async def test_synthesize_edge(tmp_path: Path) -> None:
    """Integration test: synthesize audio with edge-tts backend.

    Skipped if edge-tts is not installed.
    """
    try:
        import edge_tts  # noqa: F401
    except ImportError:
        pytest.skip("edge-tts is not installed")

    from engine.voice_engine import VoiceEngine

    llm_mock = AsyncMock()
    engine = VoiceEngine(llm=llm_mock, output_dir=str(tmp_path))

    text = "こんにちは、テスト音声です。"
    output_path = await engine.synthesize(
        text=text,
        backend="edge_tts",
        voice="ja-JP-NanamiNeural",
    )

    assert output_path is not None
    result_file = Path(output_path)
    assert result_file.exists(), f"Audio file should exist at {output_path}"
    assert result_file.stat().st_size > 0, "Audio file should not be empty"


# ------------------------------------------------------------------
# test_podcast_script_generation
# ------------------------------------------------------------------


async def test_podcast_script_generation() -> None:
    """Mock LLM and verify podcast script contains intro and outro."""
    from engine.voice_engine import VoiceEngine

    script_response = {
        "intro": "皆さん、こんにちは。Deepcast AIポッドキャストへようこそ。",
        "segments": [
            {
                "speaker": "host",
                "text": "今日はAI教育について話しましょう。",
            },
            {
                "speaker": "guest",
                "text": "AIは教育を大きく変える可能性があります。",
            },
        ],
        "outro": "お聴きいただきありがとうございました。次回もお楽しみに。",
    }

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=script_response)

    engine = VoiceEngine(llm=llm_mock)

    script = await engine.generate_podcast_script(
        topic="AI教育の未来",
        language="ja",
    )

    assert isinstance(script, dict)
    assert "intro" in script, "Script must have an intro section"
    assert "outro" in script, "Script must have an outro section"
    assert len(script["intro"]) > 0
    assert len(script["outro"]) > 0

    # Verify segments exist
    assert "segments" in script
    assert isinstance(script["segments"], list)
    assert len(script["segments"]) >= 1

    llm_mock.generate_json.assert_called_once()


async def test_podcast_script_has_speakers() -> None:
    """Podcast script segments should have speaker and text fields."""
    from engine.voice_engine import VoiceEngine

    script_response = {
        "intro": "ようこそ。",
        "segments": [
            {"speaker": "host", "text": "ホストです。"},
            {"speaker": "guest", "text": "ゲストです。"},
        ],
        "outro": "さようなら。",
    }

    llm_mock = AsyncMock()
    llm_mock.generate_json = AsyncMock(return_value=script_response)

    engine = VoiceEngine(llm=llm_mock)
    script = await engine.generate_podcast_script(topic="テスト", language="ja")

    for segment in script["segments"]:
        assert "speaker" in segment
        assert "text" in segment
        assert segment["speaker"] in ("host", "guest")

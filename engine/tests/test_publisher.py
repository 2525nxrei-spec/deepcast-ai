"""Tests for engine.publisher — Publisher with temp directory."""

from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

pytestmark = pytest.mark.asyncio


# ------------------------------------------------------------------
# Fixtures
# ------------------------------------------------------------------


@pytest.fixture()
def site_dir(tmp_path: Path) -> Path:
    """Create a minimal site structure in a temp directory."""
    # episodes.json
    episodes = [
        {
            "episode": 10,
            "title": "Episode 10 — AI入門",
            "date": "2026-03-10",
            "url": "/episodes/ep010.html",
            "audio": "/audio/ep010.mp3",
        },
        {
            "episode": 9,
            "title": "Episode 9 — Python基礎",
            "date": "2026-03-09",
            "url": "/episodes/ep009.html",
            "audio": "/audio/ep009.mp3",
        },
    ]
    episodes_file = tmp_path / "episodes.json"
    episodes_file.write_text(
        json.dumps(episodes, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    # sitemap.xml
    sitemap_content = """<?xml version="1.0" encoding="UTF-8"?>
<urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">
  <url><loc>https://deepcast-ai.com/</loc></url>
  <url><loc>https://deepcast-ai.com/episodes/ep010.html</loc></url>
  <url><loc>https://deepcast-ai.com/episodes/ep009.html</loc></url>
</urlset>
"""
    (tmp_path / "sitemap.xml").write_text(sitemap_content, encoding="utf-8")

    # service-worker.js
    sw_content = """const CACHE_NAME = 'deepcast-v3';
const URLS_TO_CACHE = [
  '/',
  '/style.css',
  '/script.js',
];
"""
    (tmp_path / "service-worker.js").write_text(sw_content, encoding="utf-8")

    # episodes directory
    episodes_dir = tmp_path / "episodes"
    episodes_dir.mkdir()

    # audio directory
    audio_dir = tmp_path / "audio"
    audio_dir.mkdir()

    return tmp_path


@pytest.fixture()
def empty_site_dir(tmp_path: Path) -> Path:
    """Site dir with no episodes.json (first episode scenario)."""
    (tmp_path / "episodes").mkdir()
    (tmp_path / "audio").mkdir()
    return tmp_path


# ------------------------------------------------------------------
# test_get_next_episode_number
# ------------------------------------------------------------------


async def test_get_next_episode_number(site_dir: Path) -> None:
    """Mock episodes.json with ep 10 as latest, verify next is 11."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    next_ep = await publisher.get_next_episode_number()

    assert next_ep == 11, f"Next episode should be 11, got {next_ep}"


async def test_get_next_episode_number_first(empty_site_dir: Path) -> None:
    """When no episodes.json exists, next episode should be 1."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(empty_site_dir))

    next_ep = await publisher.get_next_episode_number()

    assert next_ep == 1, f"First episode should be 1, got {next_ep}"


# ------------------------------------------------------------------
# test_update_episodes_json
# ------------------------------------------------------------------


async def test_update_episodes_json(site_dir: Path) -> None:
    """Verify new episode is added at the beginning of episodes.json."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    new_episode = {
        "episode": 11,
        "title": "Episode 11 — 生成AIの最前線",
        "date": "2026-03-17",
        "url": "/episodes/ep011.html",
        "audio": "/audio/ep011.mp3",
    }

    await publisher.update_episodes_json(new_episode)

    # Re-read the file
    episodes_path = site_dir / "episodes.json"
    data = json.loads(episodes_path.read_text(encoding="utf-8"))

    assert isinstance(data, list)
    assert len(data) == 3, f"Should have 3 episodes now, got {len(data)}"
    assert data[0]["episode"] == 11, "New episode should be first"
    assert data[0]["title"] == "Episode 11 — 生成AIの最前線"
    assert data[1]["episode"] == 10, "Previous latest should be second"


# ------------------------------------------------------------------
# test_update_sitemap
# ------------------------------------------------------------------


async def test_update_sitemap(site_dir: Path) -> None:
    """Verify new URL is added to sitemap.xml."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    new_url = "https://deepcast-ai.com/episodes/ep011.html"
    await publisher.update_sitemap(new_url)

    sitemap_text = (site_dir / "sitemap.xml").read_text(encoding="utf-8")

    assert new_url in sitemap_text, "New URL should appear in sitemap.xml"
    # Existing URLs should still be present
    assert "ep010.html" in sitemap_text
    assert "ep009.html" in sitemap_text


async def test_update_sitemap_no_duplicate(site_dir: Path) -> None:
    """Adding an existing URL should not create a duplicate."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    existing_url = "https://deepcast-ai.com/episodes/ep010.html"
    await publisher.update_sitemap(existing_url)

    sitemap_text = (site_dir / "sitemap.xml").read_text(encoding="utf-8")
    count = sitemap_text.count("ep010.html")
    assert count == 1, f"URL should appear only once, found {count} times"


# ------------------------------------------------------------------
# test_update_service_worker
# ------------------------------------------------------------------


async def test_update_service_worker(site_dir: Path) -> None:
    """Verify CACHE_NAME version is incremented in service-worker.js."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    await publisher.update_service_worker()

    sw_text = (site_dir / "service-worker.js").read_text(encoding="utf-8")

    # Original was 'deepcast-v3', should now be 'deepcast-v4'
    assert "deepcast-v4" in sw_text, (
        f"CACHE_NAME should be incremented to v4, got: {sw_text[:100]}"
    )
    assert "deepcast-v3" not in sw_text, "Old cache name should be replaced"


async def test_update_service_worker_first_version(tmp_path: Path) -> None:
    """If CACHE_NAME has no version number, it should become v1."""
    sw_content = "const CACHE_NAME = 'deepcast';\n"
    (tmp_path / "service-worker.js").write_text(sw_content, encoding="utf-8")

    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(tmp_path))

    await publisher.update_service_worker()

    sw_text = (tmp_path / "service-worker.js").read_text(encoding="utf-8")
    # Should have a version number now
    assert re.search(r"deepcast-v\d+", sw_text) or "deepcast-v1" in sw_text


# ------------------------------------------------------------------
# test_validate_publish
# ------------------------------------------------------------------


async def test_validate_publish(site_dir: Path) -> None:
    """Validation should pass when all required files exist."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    # Create the episode HTML and audio files
    ep_html = site_dir / "episodes" / "ep011.html"
    ep_html.write_text("<html><body>Episode 11</body></html>", encoding="utf-8")
    ep_audio = site_dir / "audio" / "ep011.mp3"
    ep_audio.write_bytes(b"\x00" * 100)  # dummy audio

    episode_data = {
        "episode": 11,
        "url": "/episodes/ep011.html",
        "audio": "/audio/ep011.mp3",
    }

    result = await publisher.validate_publish(episode_data)

    assert result["valid"] is True, f"Validation should pass: {result}"
    assert len(result.get("errors", [])) == 0


async def test_validate_publish_missing_files(site_dir: Path) -> None:
    """Validation should catch missing HTML and audio files."""
    from engine.publisher import Publisher

    publisher = Publisher(site_dir=str(site_dir))

    episode_data = {
        "episode": 99,
        "url": "/episodes/ep099.html",
        "audio": "/audio/ep099.mp3",
    }

    result = await publisher.validate_publish(episode_data)

    assert result["valid"] is False, "Validation should fail for missing files"
    assert len(result["errors"]) >= 1, "Should report at least one error"

    # Error messages should mention the missing files
    error_text = " ".join(result["errors"])
    assert "ep099" in error_text, f"Errors should reference missing file: {error_text}"

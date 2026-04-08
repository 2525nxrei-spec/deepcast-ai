"""Deepcast Engine — FastAPI bridge for serving content to external websites."""

from __future__ import annotations

import asyncio
import subprocess
import time
import uuid
from contextlib import asynccontextmanager
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

import aiosqlite
import structlog
from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse, FileResponse, Response
from pydantic import BaseModel

from config.settings import settings
from core.database import DatabaseManager

_startup_time: float = 0.0

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Database / Ollama helpers (thin wrappers – real logic lives in core/)
# ---------------------------------------------------------------------------

_db_connected: bool = False
_ollama_connected: bool = False


async def _init_database() -> None:
    """Initialize the SQLite database connection."""
    global _db_connected
    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            await db.execute("SELECT 1")
        _db_connected = True
        logger.info("database.connected", path=settings.DB_PATH)
    except Exception as exc:
        _db_connected = False
        logger.warning("database.connection_failed", error=str(exc))


async def _check_ollama() -> None:
    """Check if Ollama is reachable."""
    global _ollama_connected
    try:
        import httpx

        async with httpx.AsyncClient(timeout=5.0) as client:
            resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
            _ollama_connected = resp.status_code == 200
        logger.info("ollama.health", connected=_ollama_connected)
    except Exception as exc:
        _ollama_connected = False
        logger.warning("ollama.unreachable", error=str(exc))


async def _close_connections() -> None:
    """Clean-up on shutdown."""
    logger.info("bridge.shutdown", message="closing connections")


# ---------------------------------------------------------------------------
# Lifespan
# ---------------------------------------------------------------------------


@asynccontextmanager
async def lifespan(_app: FastAPI):
    """Startup / shutdown lifecycle."""
    global _startup_time
    _startup_time = time.time()
    logger.info("bridge.startup")
    await _init_database()
    await _check_ollama()
    yield
    await _close_connections()


# ---------------------------------------------------------------------------
# FastAPI app
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Deepcast Engine API",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# ---------------------------------------------------------------------------
# API Key dependency
# ---------------------------------------------------------------------------


async def verify_api_key(request: Request) -> None:
    """Validate the X-API-Key header against the configured secret."""
    api_key = request.headers.get("X-API-Key")
    if api_key != settings.API_SECRET_KEY:
        logger.warning("auth.failed", remote=request.client.host if request.client else "unknown")
        raise HTTPException(status_code=401, detail="Invalid or missing API key")


# ---------------------------------------------------------------------------
# Request / Response schemas
# ---------------------------------------------------------------------------


class GenerateRequest(BaseModel):
    language: str = "ja"
    topic: Optional[str] = None
    category: Optional[str] = None


class GenerateResponse(BaseModel):
    status: str = "generating"
    task_id: str


class ReviewRequest(BaseModel):
    action: str  # "approve" | "reject" | "revision"
    feedback: Optional[str] = None


# ---------------------------------------------------------------------------
# Helpers — DB queries
# ---------------------------------------------------------------------------


async def _query_contents(
    *,
    language: Optional[str] = None,
    status: str = "published",
    limit: int = 10,
    offset: int = 0,
):
    """Fetch contents from SQLite."""
    try:
        conditions: list[str] = ["status = ?"]
        params: list = [status]

        if language:
            conditions.append("language = ?")
            params.append(language)

        where = " AND ".join(conditions)

        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # total count
            count_sql = f"SELECT COUNT(*) as cnt FROM contents WHERE {where}"  # noqa: S608
            async with db.execute(count_sql, params) as cur:
                row = await cur.fetchone()
                total = row[0] if row else 0

            # rows
            data_sql = (
                f"SELECT * FROM contents WHERE {where} "  # noqa: S608
                "ORDER BY created_at DESC LIMIT ? OFFSET ?"
            )
            async with db.execute(data_sql, [*params, limit, offset]) as cur:
                rows = await cur.fetchall()
                contents = [dict(r) for r in rows]

        return contents, total
    except Exception as exc:
        logger.error("db.query_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Database query failed") from exc


async def _get_content_by_id(content_id: str):
    """Fetch a single content row by ID."""
    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT * FROM contents WHERE id = ?", [content_id]
            ) as cur:
                row = await cur.fetchone()
                if row is None:
                    raise HTTPException(status_code=404, detail="Content not found")
                return dict(row)
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("db.get_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Database query failed") from exc


# ---------------------------------------------------------------------------
# Public endpoints (no auth)
# ---------------------------------------------------------------------------


@app.get("/api/health")
async def health():
    """Public health-check endpoint."""
    return {
        "status": "ok",
        "ollama_connected": _ollama_connected,
        "db_connected": _db_connected,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/embed/latest.js")
async def embed_latest_js():
    """Return an embeddable JavaScript widget that renders latest content."""
    js_snippet = f"""\
(function() {{
  var API_URL = window.DEEPCAST_API_URL || '{settings.CORS_ORIGINS[0]}';
  var API_KEY = window.DEEPCAST_API_KEY || '';
  var COUNT   = window.DEEPCAST_COUNT || 5;

  var container = document.getElementById('deepcast-widget');
  if (!container) {{
    container = document.createElement('div');
    container.id = 'deepcast-widget';
    document.currentScript.parentNode.appendChild(container);
  }}

  container.innerHTML = '<p style="color:#888;">Loading Deepcast content\u2026</p>';

  fetch(API_URL + '/api/contents/latest?count=' + COUNT, {{
    headers: {{ 'X-API-Key': API_KEY }}
  }})
  .then(function(r) {{ return r.json(); }})
  .then(function(data) {{
    if (!data.contents || data.contents.length === 0) {{
      container.innerHTML = '<p>No content available.</p>';
      return;
    }}
    var html = '<ul style="list-style:none;padding:0;font-family:sans-serif;">';
    data.contents.forEach(function(c) {{
      html += '<li style="margin-bottom:1em;padding:0.8em;border:1px solid #e0e0e0;border-radius:6px;">';
      html += '<strong>' + (c.title || 'Untitled') + '</strong>';
      if (c.summary) html += '<p style="margin:0.4em 0 0;color:#555;font-size:0.9em;">' + c.summary + '</p>';
      html += '</li>';
    }});
    html += '</ul>';
    container.innerHTML = html;
  }})
  .catch(function() {{
    container.innerHTML = '<p style="color:red;">Failed to load content.</p>';
  }});
}})();
"""
    return Response(content=js_snippet, media_type="application/javascript; charset=utf-8")


# ---------------------------------------------------------------------------
# Authenticated endpoints
# ---------------------------------------------------------------------------


@app.get("/api/contents/latest", dependencies=[Depends(verify_api_key)])
async def contents_latest(
    language: Optional[str] = Query(None, pattern="^(ja|en)$"),
    count: int = Query(5, ge=1, le=50),
):
    """Return the latest published contents."""
    contents, _total = await _query_contents(
        language=language, status="published", limit=count, offset=0
    )
    return {"contents": contents}


@app.get("/api/contents/{content_id}", dependencies=[Depends(verify_api_key)])
async def contents_detail(content_id: str):
    """Return a single content object by ID."""
    content = await _get_content_by_id(content_id)
    return content


@app.get("/api/contents", dependencies=[Depends(verify_api_key)])
async def contents_list(
    language: Optional[str] = Query(None, pattern="^(ja|en)$"),
    status: str = Query("published"),
    limit: int = Query(10, ge=1, le=100),
    offset: int = Query(0, ge=0),
):
    """Return paginated contents list."""
    contents, total = await _query_contents(
        language=language, status=status, limit=limit, offset=offset
    )
    page = (offset // limit) + 1 if limit else 1
    return {"contents": contents, "total": total, "page": page}


@app.post("/api/generate", dependencies=[Depends(verify_api_key)])
async def generate_content(body: GenerateRequest):
    """Trigger immediate content generation via the autonomous pipeline."""
    task_id = str(uuid.uuid4())
    logger.info(
        "generate.requested",
        task_id=task_id,
        language=body.language,
        topic=body.topic,
        category=body.category,
    )

    # バックグラウンドで生成を実行
    async def _run_generation():
        try:
            from core.llm_client import LLMClient
            from engine.generator import ContentGenerator
            from engine.evaluator import ContentEvaluator
            from engine.self_manager import SelfManager

            db = DatabaseManager()
            await db.init_db()
            llm = LLMClient()
            generator = ContentGenerator(llm_client=llm, db=db)
            evaluator = ContentEvaluator(llm=llm, db=db)
            manager = SelfManager(db=db, llm=llm, generator=generator, evaluator=evaluator)
            await manager.run_autonomous_cycle(body.language)
            logger.info("generate.completed", task_id=task_id)
        except Exception as exc:
            logger.error("generate.failed", task_id=task_id, error=str(exc))

    asyncio.create_task(_run_generation())

    return GenerateResponse(status="generating", task_id=task_id)


@app.get("/api/status", dependencies=[Depends(verify_api_key)])
async def system_status():
    """Return a system status report (placeholder for SelfManager)."""
    return {
        "ollama_connected": _ollama_connected,
        "db_connected": _db_connected,
        "uptime": "unknown",
        "scheduler_running": False,
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }


@app.get("/api/quality/trend", dependencies=[Depends(verify_api_key)])
async def quality_trend(
    language: Optional[str] = Query(None, pattern="^(ja|en)$"),
    days: int = Query(7, ge=1, le=90),
):
    """Return quality score trend data over the given number of days."""
    try:
        conditions = ["status = 'published'", "created_at >= datetime('now', ?)"]
        params: list = [f"-{days} days"]

        if language:
            conditions.append("language = ?")
            params.append(language)

        where = " AND ".join(conditions)
        sql = (
            f"SELECT date(created_at) as day, "  # noqa: S608
            f"AVG(quality_score) as avg_score, "
            f"COUNT(*) as count "
            f"FROM contents WHERE {where} "
            f"GROUP BY day ORDER BY day"
        )

        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(sql, params) as cur:
                rows = await cur.fetchall()
                trend = [dict(r) for r in rows]

        return {"language": language, "days": days, "trend": trend}
    except Exception as exc:
        logger.error("quality.trend_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch quality trend") from exc


# ---------------------------------------------------------------------------
# Dashboard endpoints
# ---------------------------------------------------------------------------


@app.get("/", response_class=HTMLResponse)
async def dashboard():
    """Serve the dashboard HTML page."""
    dashboard_path = Path(__file__).parent.parent / "static" / "dashboard.html"
    if not dashboard_path.exists():
        raise HTTPException(status_code=404, detail="dashboard.html not found")
    return HTMLResponse(content=dashboard_path.read_text(encoding="utf-8"))


@app.get("/api/dashboard", dependencies=[Depends(verify_api_key)])
async def dashboard_data():
    """Return aggregated dashboard data in a single request."""
    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row

            # --- Stats ---
            async with db.execute("SELECT COUNT(*) FROM contents") as cur:
                total_contents = (await cur.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM contents WHERE status = 'published'"
            ) as cur:
                published = (await cur.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM contents WHERE status = 'published' "
                "AND date(published_at) = date('now')"
            ) as cur:
                published_today = (await cur.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM contents WHERE status = 'rejected'"
            ) as cur:
                rejected = (await cur.fetchone())[0]

            async with db.execute(
                "SELECT language, COUNT(*) as cnt FROM contents GROUP BY language"
            ) as cur:
                by_language = {row["language"]: row["cnt"] for row in await cur.fetchall()}

            async with db.execute(
                "SELECT AVG(quality_score) FROM contents WHERE quality_score > 0"
            ) as cur:
                avg_score_row = await cur.fetchone()
                avg_quality_score = round(avg_score_row[0], 1) if avg_score_row[0] else 0

            async with db.execute(
                "SELECT COUNT(*) FROM contents WHERE status = 'draft'"
            ) as cur:
                pending_reviews = (await cur.fetchone())[0]

            async with db.execute(
                "SELECT COUNT(*) FROM topics WHERE status = 'pending'"
            ) as cur:
                topics_pending = (await cur.fetchone())[0]

            # --- Audio file count ---
            audio_dir = Path(settings.TTS_OUTPUT_DIR)
            audio_files = (
                len([f for f in audio_dir.iterdir() if f.is_file()])
                if audio_dir.exists()
                else 0
            )

            stats = {
                "total_contents": total_contents,
                "published": published,
                "published_today": published_today,
                "rejected": rejected,
                "by_language": by_language,
                "avg_quality_score": avg_quality_score,
                "pending_reviews": pending_reviews,
                "audio_files": audio_files,
                "topics_pending": topics_pending,
            }

            # --- Recent contents (last 20) ---
            async with db.execute(
                "SELECT * FROM contents ORDER BY created_at DESC LIMIT 20"
            ) as cur:
                recent_contents = [dict(r) for r in await cur.fetchall()]

            # --- Quality trend (last 7 days) ---
            async with db.execute(
                "SELECT date(created_at) as day, "
                "AVG(quality_score) as avg_score, "
                "COUNT(*) as count "
                "FROM contents "
                "WHERE quality_score > 0 AND created_at >= datetime('now', '-7 days') "
                "GROUP BY day ORDER BY day"
            ) as cur:
                quality_trend_data = [dict(r) for r in await cur.fetchall()]

            # --- Pending topics ---
            async with db.execute(
                "SELECT * FROM topics WHERE status = 'pending' "
                "ORDER BY priority DESC, created_at DESC"
            ) as cur:
                topics = [dict(r) for r in await cur.fetchall()]

        # --- Health ---
        health = {"ollama": _ollama_connected, "db": _db_connected}

        # --- System info ---
        uptime_seconds = int(time.time() - _startup_time) if _startup_time else 0
        hours, remainder = divmod(uptime_seconds, 3600)
        minutes, secs = divmod(remainder, 60)
        uptime_str = f"{hours}h {minutes}m {secs}s"

        # Last generation time
        last_gen = None
        if recent_contents:
            last_gen = recent_contents[0].get("created_at")

        system_info = {
            "uptime": uptime_str,
            "last_generation": last_gen,
            "scheduler_jobs": [],
        }

        return {
            "health": health,
            "stats": stats,
            "recent_contents": recent_contents,
            "quality_trend": quality_trend_data,
            "topics": topics,
            "system": system_info,
        }
    except Exception as exc:
        logger.error("dashboard.data_failed", error=str(exc))
        raise HTTPException(status_code=500, detail="Failed to fetch dashboard data") from exc


@app.post("/api/review/{content_id}", dependencies=[Depends(verify_api_key)])
async def review_content(content_id: str, body: ReviewRequest):
    """Submit a review for a content item.

    When action is 'approve', this also:
    1. Runs Publisher.publish_episode() to generate HTML/JSON/RSS/sitemap
    2. Runs git add -A, commit, push to deploy to Cloudflare Pages
    """
    if body.action not in ("approve", "reject", "revision"):
        raise HTTPException(
            status_code=400,
            detail="action must be 'approve', 'reject', or 'revision'",
        )

    # Verify content exists
    content = await _get_content_by_id(content_id)

    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            now = datetime.now(timezone.utc).isoformat()

            if body.action == "approve":
                await db.execute(
                    "UPDATE contents SET status = 'published', published_at = ?, updated_at = ? "
                    "WHERE id = ?",
                    [now, now, content_id],
                )
                message = f"Content {content_id} published."
            elif body.action == "reject":
                await db.execute(
                    "UPDATE contents SET status = 'rejected', updated_at = ? WHERE id = ?",
                    [now, content_id],
                )
                message = f"Content {content_id} rejected."
            else:  # revision
                await db.execute(
                    "UPDATE contents SET updated_at = ? WHERE id = ?",
                    [now, content_id],
                )
                message = f"Content {content_id} marked for revision."

            # Log feedback if provided
            if body.feedback:
                await db.execute(
                    "INSERT INTO quality_logs (content_id, feedback, created_at) "
                    "VALUES (?, ?, ?)",
                    [content_id, body.feedback, now],
                )

            await db.commit()

        logger.info(
            "review.submitted",
            content_id=content_id,
            action=body.action,
            feedback=body.feedback,
        )

        # --- Publish & Deploy on approve ---
        deploy_status: dict | None = None
        if body.action == "approve":
            deploy_status = await _publish_and_deploy(content_id)

        result = {"status": "ok", "message": message}
        if deploy_status is not None:
            result["deploy"] = deploy_status
        return result
    except HTTPException:
        raise
    except Exception as exc:
        logger.error("review.failed", content_id=content_id, error=str(exc))
        raise HTTPException(status_code=500, detail="Review submission failed") from exc


async def _publish_and_deploy(content_id: str) -> dict:
    """Run Publisher then git add/commit/push to deploy to Cloudflare Pages.

    Returns a dict with publish/deploy results. Never raises — errors are
    captured in the returned dict so the review itself always succeeds.
    """
    result: dict = {"publish": None, "git_add": None, "git_commit": None, "git_push": None}
    site_root = settings.SITE_ROOT

    # --- 1. Publish (generate HTML/JSON/RSS/sitemap) ---
    try:
        from manager.publisher import Publisher

        db = DatabaseManager()
        publisher = Publisher(db=db)
        publish_results = await publisher.publish_episode(content_id)
        all_ok = all(r.success for r in publish_results)
        result["publish"] = {
            "success": all_ok,
            "files": [r.file_path for r in publish_results if r.success],
            "errors": [r.error for r in publish_results if not r.success],
        }
        logger.info(
            "deploy.publish_done",
            content_id=content_id,
            success=all_ok,
        )
        if not all_ok:
            logger.warning("deploy.publish_partial_failure", content_id=content_id)
    except Exception as exc:
        logger.error("deploy.publish_failed", content_id=content_id, error=str(exc))
        result["publish"] = {"success": False, "error": str(exc)}
        # Even if publish fails, we don't abort — return what we have
        return result

    # --- 2. Git add -A ---
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "add", "-A"],
            cwd=site_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        result["git_add"] = {
            "success": proc.returncode == 0,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
        if proc.returncode != 0:
            logger.warning("deploy.git_add_failed", stderr=proc.stderr)
            return result
    except Exception as exc:
        logger.error("deploy.git_add_error", error=str(exc))
        result["git_add"] = {"success": False, "error": str(exc)}
        return result

    # --- 3. Git commit ---
    try:
        title = (await _get_content_by_id(content_id)).get("title", "untitled")
        commit_msg = f"publish: {title} (content_id={content_id[:8]})"
        proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "commit", "-m", commit_msg],
            cwd=site_root,
            capture_output=True,
            text=True,
            timeout=30,
        )
        result["git_commit"] = {
            "success": proc.returncode == 0,
            "message": commit_msg if proc.returncode == 0 else None,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
        if proc.returncode != 0:
            logger.warning("deploy.git_commit_failed", stderr=proc.stderr)
            return result
    except Exception as exc:
        logger.error("deploy.git_commit_error", error=str(exc))
        result["git_commit"] = {"success": False, "error": str(exc)}
        return result

    # --- 4. Git push origin master ---
    try:
        proc = await asyncio.to_thread(
            subprocess.run,
            ["git", "push", "origin", "master"],
            cwd=site_root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        result["git_push"] = {
            "success": proc.returncode == 0,
            "stdout": proc.stdout.strip() if proc.stdout else None,
            "stderr": proc.stderr.strip() if proc.stderr else None,
        }
        if proc.returncode == 0:
            logger.info("deploy.git_push_success", content_id=content_id)
        else:
            logger.warning("deploy.git_push_failed", stderr=proc.stderr)
    except Exception as exc:
        logger.error("deploy.git_push_error", error=str(exc))
        result["git_push"] = {"success": False, "error": str(exc)}

    return result


@app.post("/api/generate/voice/{content_id}", dependencies=[Depends(verify_api_key)])
async def generate_voice(content_id: str):
    """Generate podcast-style voice audio for a specific content via VoiceEngine."""
    content = await _get_content_by_id(content_id)

    text = content.get("body", "")
    if not text:
        raise HTTPException(status_code=400, detail="Content body is empty")

    language = content.get("language", "ja")
    title = content.get("title", "Untitled")

    try:
        from core.voice_engine import VoiceEngine

        engine = VoiceEngine()
        audio_path = await engine.synthesize_podcast(title, text, language)

        logger.info(
            "voice.generated",
            content_id=content_id,
            language=language,
            path=str(audio_path),
        )
        return {"status": "ok", "audio_path": str(audio_path)}
    except Exception as exc:
        logger.error("voice.generation_failed", content_id=content_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Voice generation failed: {exc}") from exc


@app.post("/api/trends/analyze", dependencies=[Depends(verify_api_key)])
async def analyze_trends(
    language: Optional[str] = Query("ja", pattern="^(ja|en)$"),
):
    """Run trend analysis: content gaps, topic predictions, performance patterns."""
    task_id = str(uuid.uuid4())
    logger.info("trends.analyze.requested", task_id=task_id, language=language)

    try:
        from manager.trend_analyzer import TrendAnalyzer

        analyzer = TrendAnalyzer()

        # Run all analyses in parallel
        gaps, predictions, performance, seasonal, calendar = await asyncio.gather(
            analyzer.analyze_content_gaps(language),
            analyzer.predict_next_topics(language, count=5),
            analyzer.analyze_performance_patterns(language),
            analyzer.get_seasonal_themes(language),
            analyzer.generate_content_calendar(language, days=7),
            return_exceptions=True,
        )

        # Convert predictions to dicts (they are Pydantic models)
        predictions_list = []
        if isinstance(predictions, list):
            predictions_list = [p.model_dump() if hasattr(p, 'model_dump') else p for p in predictions]
        elif isinstance(predictions, Exception):
            logger.warning("trends.predictions_failed", error=str(predictions))

        result = {
            "status": "ok",
            "task_id": task_id,
            "language": language,
            "content_gaps": gaps if not isinstance(gaps, Exception) else [],
            "predictions": predictions_list,
            "performance": performance if not isinstance(performance, Exception) else {},
            "seasonal_themes": seasonal if not isinstance(seasonal, Exception) else [],
            "calendar": calendar if not isinstance(calendar, Exception) else [],
        }

        logger.info("trends.analyze.completed", task_id=task_id)
        return result

    except Exception as exc:
        logger.error("trends.analyze.failed", task_id=task_id, error=str(exc))
        raise HTTPException(status_code=500, detail=f"Trend analysis failed: {exc}") from exc


@app.get("/api/audio")
async def list_audio_files(api_key: str = Depends(verify_api_key)):
    """List all audio files with metadata, resolving episode titles from DB."""
    import json as _json
    import re
    import urllib.parse

    audio_dir = Path(__file__).parent.parent / "data" / "audio"
    # Also check the site episodes directory
    site_episodes = Path(settings.SITE_ROOT) / "episodes"

    # Build a lookup: audio filename -> content title from the database
    audio_title_map: dict[str, str] = {}
    try:
        async with aiosqlite.connect(settings.DB_PATH) as db:
            db.row_factory = aiosqlite.Row
            async with db.execute(
                "SELECT title, metadata FROM contents WHERE metadata IS NOT NULL"
            ) as cur:
                rows = await cur.fetchall()
                for row in rows:
                    try:
                        meta = _json.loads(row["metadata"]) if row["metadata"] else {}
                        ap = meta.get("audio_path", "")
                        if ap:
                            # audio_path may be a full path; extract just the filename
                            audio_filename = Path(ap).name
                            audio_title_map[audio_filename] = row["title"]
                    except (_json.JSONDecodeError, TypeError):
                        pass
    except Exception as exc:
        logger.warning("audio.title_lookup_failed", error=str(exc))

    def _clean_filename(filename: str) -> str:
        """Fallback: clean up raw filename into a readable display name."""
        name = filename.rsplit(".", 1)[0]  # strip extension
        # Remove leading language prefix like "ja_" or "en_"
        name = re.sub(r"^(ja|en)_", "", name)
        # Remove numeric timestamps (10+ digit sequences)
        name = re.sub(r"\d{10,}", "", name)
        # Replace underscores / hyphens with spaces, collapse whitespace
        name = name.replace("_", " ").replace("-", " ")
        name = re.sub(r"\s+", " ", name).strip()
        # URL-decode any percent-encoded Japanese characters
        name = urllib.parse.unquote(name)
        return name if name else filename

    def _resolve_title(filename: str) -> str:
        """Return DB title if matched, otherwise a cleaned-up filename."""
        if filename in audio_title_map:
            return audio_title_map[filename]
        return _clean_filename(filename)

    files = []
    # Engine audio
    if audio_dir.exists():
        for f in sorted(audio_dir.glob("*.mp3")):
            files.append({
                "name": f.name,
                "display_name": _resolve_title(f.name),
                "path": f"/api/audio/play/{f.name}",
                "size": f.stat().st_size,
                "source": "engine",
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
    # Site episodes audio
    if site_episodes.exists():
        for f in sorted(site_episodes.glob("*.mp3")):
            files.append({
                "name": f.name,
                "display_name": _resolve_title(f.name),
                "path": f"/api/audio/play/{f.name}",
                "size": f.stat().st_size,
                "source": "site",
                "created": datetime.fromtimestamp(f.stat().st_mtime).isoformat()
            })
    return {"files": files, "total": len(files)}


@app.get("/api/audio/play/{filename}")
async def play_audio(filename: str):
    """Stream an audio file."""
    # Security: only allow .mp3 files, no path traversal
    if ".." in filename or "/" in filename or "\\" in filename:
        raise HTTPException(400, "Invalid filename")
    if not filename.endswith(".mp3"):
        raise HTTPException(400, "Only .mp3 files supported")

    # Check engine audio dir first
    audio_path = Path(__file__).parent.parent / "data" / "audio" / filename
    if not audio_path.exists():
        # Check site episodes dir
        audio_path = Path(settings.SITE_ROOT) / "episodes" / filename

    if not audio_path.exists():
        raise HTTPException(404, "Audio file not found")

    return FileResponse(audio_path, media_type="audio/mpeg", filename=filename)

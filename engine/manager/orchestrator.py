"""Deepcast Engine — Supreme Autonomous Orchestrator.

Brain + Voice + Trends + Publisher を統合し、
完全自律のコンテンツ生成・公開ループを実現する。
"""

from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
from typing import Any, TYPE_CHECKING

import structlog

if TYPE_CHECKING:
    from core.database import DatabaseManager
    from core.brain import Brain
    from manager.trend_analyzer import TrendAnalyzer
    from core.voice_engine import VoiceEngine
    from manager.publisher import Publisher
    from engine.self_manager import SelfManager

logger = structlog.get_logger(__name__)


class Orchestrator:
    """The Supreme Autonomous Operator.

    Connects Brain + Voice + Trends + Publisher into one continuous loop.
    """

    def __init__(
        self,
        db: DatabaseManager,
        brain: Brain,
        trend_analyzer: TrendAnalyzer,
        voice_engine: VoiceEngine,
        publisher: Publisher,
        self_manager: SelfManager,
    ) -> None:
        self._db = db
        self._brain = brain
        self._trend_analyzer = trend_analyzer
        self._voice_engine = voice_engine
        self._publisher = publisher
        self._self_manager = self_manager

    # ------------------------------------------------------------------
    # 1. run_full_autonomous_cycle
    # ------------------------------------------------------------------

    async def run_full_autonomous_cycle(self) -> dict:
        """完全自律サイクルを実行する.

        Step 1: トレンド分析 — 日英の次回トピックを予測
        Step 2: Brain パイプライン — 企画 -> 生成 -> 評価 -> 公開
        Step 3: 音声生成 — 新規コンテンツのポッドキャスト音声を合成
        Step 4: 公開 — 音声付きコンテンツをサイトに公開
        Step 5: 検証 — 公開済みエピソードのバリデーション
        Step 6: プロンプト最適化 — 必要に応じて自己改善

        Returns:
            各ステップの結果を含むステータスレポート dict
        """
        cycle_start = datetime.now(timezone.utc)
        report: dict[str, Any] = {
            "cycle_start": cycle_start.isoformat(),
            "trends": {},
            "brain_pipeline": {},
            "voice_generation": {},
            "publishing": {},
            "validation": {},
            "optimization": {},
            "errors": [],
        }

        # --- Step 1: Trend Analysis ------------------------------------------
        logger.info("orchestrator.step1.trend_analysis.start")
        try:
            for lang in ("ja", "en"):
                predictions = await self._trend_analyzer.predict_next_topics(lang)
                report["trends"][lang] = {
                    "topics": predictions if predictions else [],
                    "count": len(predictions) if predictions else 0,
                }
            logger.info("orchestrator.step1.trend_analysis.done", trends=report["trends"])
        except Exception as exc:
            logger.exception("orchestrator.step1.trend_analysis.error")
            report["errors"].append(f"trend_analysis: {exc}")

        # --- Step 2: Brain Pipeline ------------------------------------------
        logger.info("orchestrator.step2.brain_pipeline.start")
        try:
            pipeline_result = await self._brain.run_dual_language_pipeline()
            report["brain_pipeline"] = pipeline_result if isinstance(pipeline_result, dict) else {"result": pipeline_result}
            logger.info("orchestrator.step2.brain_pipeline.done", result=pipeline_result)
        except Exception as exc:
            logger.exception("orchestrator.step2.brain_pipeline.error")
            report["errors"].append(f"brain_pipeline: {exc}")

        # --- Step 3: Voice Generation ----------------------------------------
        logger.info("orchestrator.step3.voice_generation.start")
        try:
            conn = await self._db._get_connection()
            cursor = await conn.execute(
                """SELECT id, title, body, language FROM contents
                   WHERE status = 'published' AND audio_path IS NULL
                   ORDER BY created_at DESC""",
            )
            rows = await cursor.fetchall()

            generated_audio: list[dict] = []
            for row in rows:
                try:
                    audio_path = await self._voice_engine.synthesize_podcast(
                        title=row["title"],
                        body=row["body"],
                        language=row["language"],
                    )
                    if audio_path:
                        await conn.execute(
                            "UPDATE contents SET audio_path = ? WHERE id = ?",
                            (str(audio_path), row["id"]),
                        )
                        await conn.commit()
                        generated_audio.append({
                            "content_id": row["id"],
                            "title": row["title"],
                            "audio_path": str(audio_path),
                        })
                except Exception as exc:
                    logger.exception(
                        "orchestrator.step3.voice_generation.item_error",
                        content_id=row["id"],
                    )
                    report["errors"].append(f"voice_generation[{row['id']}]: {exc}")

            report["voice_generation"] = {
                "pending": len(rows),
                "generated": len(generated_audio),
                "items": generated_audio,
            }
            logger.info(
                "orchestrator.step3.voice_generation.done",
                generated=len(generated_audio),
            )
        except Exception as exc:
            logger.exception("orchestrator.step3.voice_generation.error")
            report["errors"].append(f"voice_generation: {exc}")

        # --- Step 4: Publish -------------------------------------------------
        logger.info("orchestrator.step4.publishing.start")
        try:
            cursor = await conn.execute(
                """SELECT id, title, language, audio_path FROM contents
                   WHERE status = 'published' AND audio_path IS NOT NULL
                   ORDER BY created_at DESC""",
            )
            publishable = await cursor.fetchall()

            published_ids: list[int] = []
            for row in publishable:
                try:
                    result = await self._publisher.publish_episode(
                        content_id=row["id"],
                    )
                    if result:
                        published_ids.append(row["id"])
                except Exception as exc:
                    logger.exception(
                        "orchestrator.step4.publishing.item_error",
                        content_id=row["id"],
                    )
                    report["errors"].append(f"publish[{row['id']}]: {exc}")

            report["publishing"] = {
                "candidates": len(publishable),
                "published": len(published_ids),
                "ids": published_ids,
            }
            logger.info(
                "orchestrator.step4.publishing.done",
                published=len(published_ids),
            )
        except Exception as exc:
            logger.exception("orchestrator.step4.publishing.error")
            report["errors"].append(f"publishing: {exc}")

        # --- Step 5: Validate ------------------------------------------------
        # Note: publish_episode already runs validate_publish internally.
        # Here we log that validation was delegated to the publisher.
        logger.info("orchestrator.step5.validation.start")
        report["validation"] = {
            "total": len(published_ids),
            "note": "Validation is performed within publish_episode for each item.",
            "ids": published_ids,
        }
        logger.info("orchestrator.step5.validation.done", published_ids=published_ids)

        # --- Step 6: Prompt Optimization (if needed) -------------------------
        logger.info("orchestrator.step6.optimization.start")
        try:
            optimization_results: dict[str, bool] = {}
            for lang in ("ja", "en"):
                try:
                    optimized = await self._self_manager.optimize_prompts(lang)
                    optimization_results[lang] = optimized
                except Exception as exc:
                    logger.exception(
                        "orchestrator.step6.optimization.lang_error",
                        language=lang,
                    )
                    optimization_results[lang] = False
                    report["errors"].append(f"optimize[{lang}]: {exc}")

            report["optimization"] = optimization_results
            logger.info("orchestrator.step6.optimization.done", results=optimization_results)
        except Exception as exc:
            logger.exception("orchestrator.step6.optimization.error")
            report["errors"].append(f"optimization: {exc}")

        # --- Finalize --------------------------------------------------------
        cycle_end = datetime.now(timezone.utc)
        report["cycle_end"] = cycle_end.isoformat()
        report["elapsed_seconds"] = round((cycle_end - cycle_start).total_seconds(), 1)
        report["success"] = len(report["errors"]) == 0

        logger.info(
            "orchestrator.cycle_complete",
            elapsed=report["elapsed_seconds"],
            errors=len(report["errors"]),
        )

        await self._db.save_system_log(
            level="INFO" if report["success"] else "WARNING",
            message=f"Autonomous cycle completed in {report['elapsed_seconds']}s "
                    f"with {len(report['errors'])} error(s)",
            component="orchestrator",
        )

        return report

    # ------------------------------------------------------------------
    # 2. get_system_health
    # ------------------------------------------------------------------

    async def get_system_health(self) -> dict:
        """システム全体のヘルスチェックを実行する.

        チェック項目:
        - Ollama 接続
        - DB 接続
        - TTS バックエンド
        - 音声ファイル用ディスク容量
        - 最終成功実行時刻

        Returns:
            ヘルスステータス dict
        """
        import httpx
        from config.settings import settings

        health: dict[str, Any] = {
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "ollama": {"status": "unknown"},
            "database": {"status": "unknown"},
            "tts_backends": {"status": "unknown"},
            "disk_space": {"status": "unknown"},
            "last_successful_run": None,
        }

        # --- Ollama ----------------------------------------------------------
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                resp.raise_for_status()
                models = resp.json().get("models", [])
            health["ollama"] = {
                "status": "healthy",
                "url": settings.OLLAMA_BASE_URL,
                "models_available": len(models),
            }
        except Exception as exc:
            health["ollama"] = {
                "status": "unhealthy",
                "url": settings.OLLAMA_BASE_URL,
                "error": str(exc),
            }

        # --- Database --------------------------------------------------------
        try:
            conn = await self._db._get_connection()
            cursor = await conn.execute("SELECT COUNT(*) as cnt FROM contents")
            row = await cursor.fetchone()
            health["database"] = {
                "status": "healthy",
                "total_contents": row["cnt"] if row else 0,
            }
        except Exception as exc:
            health["database"] = {
                "status": "unhealthy",
                "error": str(exc),
            }

        # --- TTS Backends ----------------------------------------------------
        try:
            tts_available = hasattr(self._voice_engine, "check_backends")
            if tts_available:
                tts_status = await self._voice_engine.check_backends()
                health["tts_backends"] = {
                    "status": "healthy" if tts_status else "degraded",
                    "details": tts_status,
                }
            else:
                health["tts_backends"] = {"status": "available"}
        except Exception as exc:
            health["tts_backends"] = {
                "status": "unhealthy",
                "error": str(exc),
            }

        # --- Disk Space (for audio) ------------------------------------------
        try:
            audio_dir = Path(settings.DB_PATH).resolve().parent / "audio"
            if audio_dir.exists():
                usage = shutil.disk_usage(str(audio_dir))
            else:
                usage = shutil.disk_usage(str(Path(settings.DB_PATH).resolve().parent))
            free_gb = round(usage.free / (1024 ** 3), 2)
            health["disk_space"] = {
                "status": "healthy" if free_gb > 1.0 else "warning",
                "free_gb": free_gb,
                "total_gb": round(usage.total / (1024 ** 3), 2),
            }
        except Exception as exc:
            health["disk_space"] = {
                "status": "unknown",
                "error": str(exc),
            }

        # --- Last Successful Run ---------------------------------------------
        try:
            conn = await self._db._get_connection()
            cursor = await conn.execute(
                """SELECT created_at FROM system_logs
                   WHERE component = 'orchestrator'
                     AND level = 'INFO'
                     AND message LIKE '%cycle completed%'
                   ORDER BY created_at DESC LIMIT 1""",
            )
            row = await cursor.fetchone()
            if row:
                health["last_successful_run"] = row["created_at"]
        except Exception:
            pass

        # --- Overall ---------------------------------------------------------
        statuses = [
            health["ollama"]["status"],
            health["database"]["status"],
            health["tts_backends"]["status"],
            health["disk_space"]["status"],
        ]
        if all(s == "healthy" for s in statuses):
            health["overall"] = "healthy"
        elif any(s == "unhealthy" for s in statuses):
            health["overall"] = "unhealthy"
        else:
            health["overall"] = "degraded"

        logger.info("orchestrator.health_check", overall=health["overall"])
        return health

    # ------------------------------------------------------------------
    # 3. get_dashboard_data
    # ------------------------------------------------------------------

    async def get_dashboard_data(self) -> dict:
        """ダッシュボード表示用のデータを集約する.

        Returns:
            dict containing:
            - total_contents (ja/en 別)
            - published_today
            - quality_scores (平均・最高・最低)
            - pending_topics
            - audio_files_generated
            - last_pipeline_run
        """
        now = datetime.now(timezone.utc)
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()

        dashboard: dict[str, Any] = {
            "timestamp": now.isoformat(),
            "total_contents": {"ja": 0, "en": 0},
            "published_today": {"ja": 0, "en": 0},
            "quality_scores": {"avg": 0.0, "max": 0.0, "min": 0.0},
            "pending_topics": {"ja": 0, "en": 0},
            "audio_files_generated": 0,
            "last_pipeline_run": None,
        }

        try:
            conn = await self._db._get_connection()

            # --- Total contents per language ---------------------------------
            cursor = await conn.execute(
                """SELECT language, COUNT(*) as cnt FROM contents
                   GROUP BY language""",
            )
            for row in await cursor.fetchall():
                lang = row["language"]
                if lang in ("ja", "en"):
                    dashboard["total_contents"][lang] = row["cnt"]

            # --- Published today per language --------------------------------
            cursor = await conn.execute(
                """SELECT language, COUNT(*) as cnt FROM contents
                   WHERE status = 'published' AND created_at >= ?
                   GROUP BY language""",
                (today_start,),
            )
            for row in await cursor.fetchall():
                lang = row["language"]
                if lang in ("ja", "en"):
                    dashboard["published_today"][lang] = row["cnt"]

            # --- Quality scores (last 7 days) --------------------------------
            cursor = await conn.execute(
                """SELECT AVG(score) as avg_s, MAX(score) as max_s, MIN(score) as min_s
                   FROM quality_logs
                   WHERE created_at >= DATE('now', '-7 days')""",
            )
            qrow = await cursor.fetchone()
            if qrow and qrow["avg_s"] is not None:
                dashboard["quality_scores"] = {
                    "avg": round(qrow["avg_s"], 1),
                    "max": round(qrow["max_s"], 1),
                    "min": round(qrow["min_s"], 1),
                }

            # --- Pending topics per language ---------------------------------
            cursor = await conn.execute(
                """SELECT language, COUNT(*) as cnt FROM topics
                   WHERE status = 'pending'
                   GROUP BY language""",
            )
            for row in await cursor.fetchall():
                lang = row["language"]
                if lang in ("ja", "en"):
                    dashboard["pending_topics"][lang] = row["cnt"]

            # --- Audio files generated ---------------------------------------
            cursor = await conn.execute(
                "SELECT COUNT(*) as cnt FROM contents WHERE audio_path IS NOT NULL",
            )
            arow = await cursor.fetchone()
            dashboard["audio_files_generated"] = arow["cnt"] if arow else 0

            # --- Last pipeline run -------------------------------------------
            cursor = await conn.execute(
                """SELECT created_at FROM system_logs
                   WHERE component IN ('orchestrator', 'scheduler')
                     AND message LIKE '%pipeline%completed%'
                   ORDER BY created_at DESC LIMIT 1""",
            )
            lrow = await cursor.fetchone()
            if lrow:
                dashboard["last_pipeline_run"] = lrow["created_at"]

        except Exception:
            logger.exception("orchestrator.dashboard_data.error")

        logger.info("orchestrator.dashboard_data.collected")
        return dashboard

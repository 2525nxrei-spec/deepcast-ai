"""Deepcast Engine — APScheduler ベースの自律ループワーカー."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import TYPE_CHECKING

import httpx
import structlog
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.events import EVENT_JOB_ERROR, EVENT_JOB_MISSED, JobExecutionEvent

from config.settings import settings
from core.database import DatabaseManager

if TYPE_CHECKING:
    from core.brain import Brain
    from manager.trend_analyzer import TrendAnalyzer
    from core.voice_engine import VoiceEngine

logger = structlog.get_logger(__name__)


class AutonomousWorker:
    """APScheduler を使った自律コンテンツ生成ワーカー."""

    def __init__(
        self,
        db: DatabaseManager,
        self_manager: object | None = None,
        brain: Brain | None = None,
        trend_analyzer: TrendAnalyzer | None = None,
        voice_engine: VoiceEngine | None = None,
    ) -> None:
        self._db = db
        self._self_manager = self_manager
        self._brain = brain
        self._trend_analyzer = trend_analyzer
        self._voice_engine = voice_engine
        self._scheduler = AsyncIOScheduler(
            job_defaults={
                "coalesce": True,
                "max_instances": 1,
                "misfire_grace_time": 300,
            },
        )
        self._scheduler.add_listener(self._on_job_error, EVENT_JOB_ERROR)
        self._scheduler.add_listener(self._on_job_missed, EVENT_JOB_MISSED)

    # ------------------------------------------------------------------
    # public API
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """スケジューラを起動し、全ジョブを登録する."""
        logger.info("worker.starting")

        # 1) コンテンツ生成サイクル
        self._scheduler.add_job(
            self._content_generation_cycle,
            "interval",
            hours=settings.SCHEDULE_INTERVAL_HOURS,
            id="content_generation_cycle",
            name="Content Generation Cycle",
            # next_run_time=datetime.now(),  # 起動直後の即実行は無効化（サーバー起動を妨げるため）
        )

        # 2) プロンプト最適化
        self._scheduler.add_job(
            self._prompt_optimization,
            "interval",
            hours=6,
            id="prompt_optimization",
            name="Prompt Optimization",
        )

        # 3) 古いログのクリーンアップ（毎日 03:00）
        self._scheduler.add_job(
            self._cleanup_old_logs,
            "cron",
            hour=3,
            minute=0,
            id="cleanup_old_logs",
            name="Cleanup Old Logs",
        )

        # 4) ヘルスチェック（5分ごと）
        self._scheduler.add_job(
            self._health_check,
            "interval",
            minutes=5,
            id="health_check",
            name="Health Check",
        )

        # 5) Brain パイプライン（2時間ごと）
        if self._brain is not None:
            self._scheduler.add_job(
                self._brain_pipeline,
                "interval",
                hours=2,
                id="brain_pipeline",
                name="Brain Dual-Language Pipeline",
            )

        # 6) トレンド分析（12時間ごと）
        if self._trend_analyzer is not None:
            self._scheduler.add_job(
                self._trend_analysis,
                "interval",
                hours=12,
                id="trend_analysis",
                name="Trend Analysis",
            )

        # 7) 音声生成（3時間ごと）
        if self._voice_engine is not None:
            self._scheduler.add_job(
                self._voice_generation,
                "interval",
                hours=3,
                id="voice_generation",
                name="Voice Generation",
            )

        self._scheduler.start()
        logger.info(
            "worker.started",
            interval_hours=settings.SCHEDULE_INTERVAL_HOURS,
            jobs=[j.id for j in self._scheduler.get_jobs()],
        )

    async def stop(self) -> None:
        """スケジューラをグレースフルに停止する."""
        logger.info("worker.stopping")
        if self._scheduler.running:
            self._scheduler.shutdown(wait=True)
        logger.info("worker.stopped")

    async def run_once(self) -> dict:
        """単発で1サイクル実行する（テスト・CLI 用）.

        Returns:
            run_full_cycle の戻り値（dict）。
        """
        logger.info("worker.run_once")
        return await self._content_generation_cycle()

    # ------------------------------------------------------------------
    # scheduled jobs
    # ------------------------------------------------------------------

    async def _content_generation_cycle(self) -> dict:
        """self_manager.run_full_cycle() を呼び出す."""
        logger.info("job.content_generation_cycle.start")
        if self._self_manager is None:
            logger.warning("job.content_generation_cycle.skipped", reason="no self_manager")
            return {}

        try:
            result = await self._self_manager.run_full_cycle()
            logger.info("job.content_generation_cycle.done", result=result)
            await self._db.save_system_log(
                level="INFO",
                message=f"Content generation cycle completed: {result}",
                component="scheduler",
            )
            return result
        except Exception:
            logger.exception("job.content_generation_cycle.error")
            await self._db.save_system_log(
                level="ERROR",
                message="Content generation cycle failed",
                component="scheduler",
            )
            raise

    async def _prompt_optimization(self) -> None:
        """プロンプトのパフォーマンスを確認し、必要に応じて最適化する."""
        logger.info("job.prompt_optimization.start")
        try:
            for prompt_type in ("generate", "evaluate"):
                perf = await self._db.get_prompt_performance(prompt_type)
                if perf is None:
                    logger.info(
                        "job.prompt_optimization.no_data",
                        prompt_type=prompt_type,
                    )
                    continue

                avg_score = perf.get("avg_score", 0)
                if avg_score < settings.QUALITY_THRESHOLD:
                    logger.warning(
                        "job.prompt_optimization.low_score",
                        prompt_type=prompt_type,
                        avg_score=avg_score,
                        threshold=settings.QUALITY_THRESHOLD,
                    )
                    # SelfManager.optimize_prompts() がこの機能を担当

            logger.info("job.prompt_optimization.done")
        except Exception:
            logger.exception("job.prompt_optimization.error")
            raise

    async def _cleanup_old_logs(self) -> None:
        """30日以上前の system_logs を削除する."""
        logger.info("job.cleanup_old_logs.start")
        try:
            db = await self._db._get_connection()
            cursor = await db.execute(
                "DELETE FROM system_logs WHERE created_at < DATE('now', '-30 days')",
            )
            await db.commit()
            deleted = cursor.rowcount
            logger.info("job.cleanup_old_logs.done", deleted_rows=deleted)
        except Exception:
            logger.exception("job.cleanup_old_logs.error")
            raise

    async def _brain_pipeline(self) -> None:
        """Brain の日英デュアル言語パイプラインを実行する."""
        logger.info("job.brain_pipeline.start")
        try:
            result = await self._brain.run_dual_language_pipeline()
            logger.info("job.brain_pipeline.done", result=result)
            await self._db.save_system_log(
                level="INFO",
                message=f"Brain pipeline completed: {result}",
                component="scheduler",
            )
        except Exception:
            logger.exception("job.brain_pipeline.error")
            await self._db.save_system_log(
                level="ERROR",
                message="Brain pipeline failed",
                component="scheduler",
            )
            raise

    async def _trend_analysis(self) -> None:
        """日英両方のトレンド分析・次回トピック予測を実行する."""
        logger.info("job.trend_analysis.start")
        try:
            for lang in ("ja", "en"):
                predictions = await self._trend_analyzer.predict_next_topics(lang)
                logger.info(
                    "job.trend_analysis.predicted",
                    language=lang,
                    topic_count=len(predictions) if predictions else 0,
                )
            await self._db.save_system_log(
                level="INFO",
                message="Trend analysis completed for ja/en",
                component="scheduler",
            )
            logger.info("job.trend_analysis.done")
        except Exception:
            logger.exception("job.trend_analysis.error")
            await self._db.save_system_log(
                level="ERROR",
                message="Trend analysis failed",
                component="scheduler",
            )
            raise

    async def _voice_generation(self) -> None:
        """公開済みで音声未生成のコンテンツに音声を生成する."""
        import json as _json

        logger.info("job.voice_generation.start")
        try:
            conn = await self._db._get_connection()
            cursor = await conn.execute(
                """SELECT id, title, body, language, metadata FROM contents
                   WHERE status = 'published'
                     AND (metadata IS NULL
                          OR json_extract(metadata, '$.audio_path') IS NULL)
                   ORDER BY created_at DESC""",
            )
            rows = await cursor.fetchall()

            generated_count = 0
            for row in rows:
                try:
                    audio_path = await self._voice_engine.synthesize_podcast(
                        title=row["title"],
                        body=row["body"],
                        language=row["language"],
                    )
                    if audio_path:
                        # metadata JSON に audio_path を追加
                        existing = row["metadata"]
                        meta = _json.loads(existing) if existing else {}
                        meta["audio_path"] = str(audio_path)
                        await conn.execute(
                            "UPDATE contents SET metadata = ? WHERE id = ?",
                            (_json.dumps(meta, ensure_ascii=False), row["id"]),
                        )
                        await conn.commit()
                        generated_count += 1
                        logger.info(
                            "job.voice_generation.generated",
                            content_id=row["id"],
                            audio_path=str(audio_path),
                        )
                except Exception:
                    logger.exception(
                        "job.voice_generation.item_error",
                        content_id=row["id"],
                    )

            await self._db.save_system_log(
                level="INFO",
                message=f"Voice generation completed: {generated_count} files generated",
                component="scheduler",
            )
            logger.info("job.voice_generation.done", generated_count=generated_count)
        except Exception:
            logger.exception("job.voice_generation.error")
            await self._db.save_system_log(
                level="ERROR",
                message="Voice generation failed",
                component="scheduler",
            )
            raise

    async def _health_check(self) -> None:
        """Ollama の接続を確認する."""
        try:
            async with httpx.AsyncClient(timeout=10.0) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                resp.raise_for_status()
            logger.debug("job.health_check.ok", ollama_url=settings.OLLAMA_BASE_URL)
        except Exception as exc:
            logger.error(
                "job.health_check.failed",
                ollama_url=settings.OLLAMA_BASE_URL,
                error=str(exc),
            )
            await self._db.save_system_log(
                level="ERROR",
                message=f"Ollama health check failed: {exc}",
                component="health_check",
            )

    # ------------------------------------------------------------------
    # event listeners
    # ------------------------------------------------------------------

    def _on_job_error(self, event: JobExecutionEvent) -> None:
        """ジョブがエラーで終了したときのリスナー."""
        logger.error(
            "scheduler.job_error",
            job_id=event.job_id,
            exception=str(event.exception),
            traceback=str(event.traceback),
        )

    def _on_job_missed(self, event: JobExecutionEvent) -> None:
        """ジョブが実行漏れしたときのリスナー."""
        logger.warning(
            "scheduler.job_missed",
            job_id=event.job_id,
            scheduled_run_time=str(event.scheduled_run_time),
        )

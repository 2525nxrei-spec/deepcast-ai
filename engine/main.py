"""Deepcast Engine — メインエントリーポイント.

Usage:
    python main.py serve            # FastAPI + スケジューラ起動
    python main.py generate         # 1サイクル実行して終了
    python main.py status           # システムステータス表示
    python main.py init             # DB 初期化のみ
    python main.py pipeline         # Brain デュアル言語パイプラインを1回実行
    python main.py voice            # 音声未生成コンテンツの音声を生成
    python main.py trends           # トレンド分析とコンテンツカレンダーを表示
    python main.py publish          # 最新コンテンツをサイトに公開
"""

from __future__ import annotations

import argparse
import asyncio
import io
import signal
import sys
from typing import Any

import logging

import structlog
import uvicorn

from config.settings import settings

# ---------------------------------------------------------------------------
# structlog 設定（JSON フォーマット）
# ---------------------------------------------------------------------------

_LOG_LEVELS = {
    "DEBUG": logging.DEBUG,
    "INFO": logging.INFO,
    "WARNING": logging.WARNING,
    "ERROR": logging.ERROR,
    "CRITICAL": logging.CRITICAL,
}

structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(
        _LOG_LEVELS.get(settings.LOG_LEVEL.upper(), logging.INFO),
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("deepcast.main")

# ---------------------------------------------------------------------------
# helpers
# ---------------------------------------------------------------------------


async def _init_components() -> tuple[Any, Any, Any]:
    """DB・SelfManager・Worker を初期化して返す."""
    from core.database import DatabaseManager
    from core.llm_client import LLMClient
    from engine.evaluator import ContentEvaluator
    from engine.generator import ContentGenerator
    from engine.self_manager import SelfManager
    from scheduler.worker import AutonomousWorker

    db = DatabaseManager()
    await db.init_db()

    llm = LLMClient()
    generator = ContentGenerator(llm_client=llm, db=db)
    evaluator = ContentEvaluator(llm=llm, db=db)
    self_manager = SelfManager(db=db, llm=llm, generator=generator, evaluator=evaluator)
    worker = AutonomousWorker(db=db, self_manager=self_manager)

    return db, self_manager, worker


async def _init_full_components() -> dict[str, Any]:
    """全モジュール（Brain, TrendAnalyzer, VoiceEngine, Publisher）を含む初期化."""
    from core.database import DatabaseManager
    from core.llm_client import LLMClient
    from engine.evaluator import ContentEvaluator
    from engine.generator import ContentGenerator
    from engine.self_manager import SelfManager
    from core.brain import Brain
    from manager.trend_analyzer import TrendAnalyzer
    from core.voice_engine import VoiceEngine
    from manager.publisher import Publisher
    from scheduler.worker import AutonomousWorker

    db = DatabaseManager()
    await db.init_db()

    llm = LLMClient()
    generator = ContentGenerator(llm_client=llm, db=db)
    evaluator = ContentEvaluator(llm=llm, db=db)
    self_manager = SelfManager(db=db, llm=llm, generator=generator, evaluator=evaluator)

    brain = Brain(db=db, llm=llm, generator=generator, evaluator=evaluator)
    trend_analyzer = TrendAnalyzer(db=db, llm=llm)
    voice_engine = VoiceEngine()
    publisher = Publisher(db=db)

    worker = AutonomousWorker(
        db=db,
        self_manager=self_manager,
        brain=brain,
        trend_analyzer=trend_analyzer,
        voice_engine=voice_engine,
    )

    return {
        "db": db,
        "llm": llm,
        "self_manager": self_manager,
        "brain": brain,
        "trend_analyzer": trend_analyzer,
        "voice_engine": voice_engine,
        "publisher": publisher,
        "worker": worker,
    }


# ---------------------------------------------------------------------------
# commands
# ---------------------------------------------------------------------------


async def cmd_serve(host: str, port: int, no_scheduler: bool) -> None:
    """FastAPI サーバー + スケジューラを起動する."""
    components = await _init_full_components()
    db = components["db"]
    worker = components["worker"]
    shutdown_event = asyncio.Event()

    # --- graceful shutdown -----------------------------------------------
    def _handle_signal() -> None:
        logger.info("shutdown.signal_received")
        shutdown_event.set()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, _handle_signal)
        except NotImplementedError:
            # Windows では add_signal_handler が使えないので signal.signal で代替
            signal.signal(sig, lambda s, f: _handle_signal())

    # --- scheduler -------------------------------------------------------
    if not no_scheduler:
        await worker.start()
        logger.info("serve.scheduler_started")
    else:
        logger.info("serve.scheduler_skipped")

    # --- uvicorn ---------------------------------------------------------
    logger.info("serve.starting", host=host, port=port)

    from api.bridge import app  # noqa: E402 — FastAPI app

    config = uvicorn.Config(
        app=app,
        host=host,
        port=port,
        log_level=settings.LOG_LEVEL.lower(),
        loop="asyncio",
    )
    server = uvicorn.Server(config)

    try:
        await server.serve()
    finally:
        if not no_scheduler:
            await worker.stop()
        await db.close()
        logger.info("serve.stopped")


async def cmd_generate() -> None:
    """1サイクル実行して終了する."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    db, self_manager, worker = await _init_components()

    try:
        logger.info("generate.start")
        result = await worker.run_once()

        logger.info("generate.done", result=result)
        print("\n--- Generation Result ---")
        if isinstance(result, dict):
            for key, value in result.items():
                print(f"  {key}: {value}")
        else:
            print(f"  {result}")
        print("-------------------------\n")
    finally:
        await db.close()


async def cmd_status() -> None:
    """システムステータスを表示する."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    from core.database import DatabaseManager

    db = DatabaseManager()
    await db.init_db()

    try:
        conn = await db._get_connection()

        # コンテンツ集計
        cursor = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM contents GROUP BY status"
        )
        content_stats = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

        # トピック集計
        cursor = await conn.execute(
            "SELECT status, COUNT(*) as cnt FROM topics GROUP BY status"
        )
        topic_stats = {row["status"]: row["cnt"] for row in await cursor.fetchall()}

        # 最新品質スコア
        cursor = await conn.execute(
            "SELECT AVG(score) as avg_score, COUNT(*) as cnt "
            "FROM quality_logs "
            "WHERE created_at >= DATE('now', '-7 days')"
        )
        quality_row = await cursor.fetchone()
        avg_quality = round(quality_row["avg_score"], 1) if quality_row["avg_score"] else 0
        quality_count = quality_row["cnt"]

        # Ollama 接続確認
        import httpx

        ollama_ok = False
        try:
            async with httpx.AsyncClient(timeout=5.0) as client:
                resp = await client.get(f"{settings.OLLAMA_BASE_URL}/api/tags")
                ollama_ok = resp.status_code == 200
        except Exception:
            pass

        print("\n=== Deepcast Engine Status ===")
        print(f"  Ollama:         {'Connected' if ollama_ok else 'Disconnected'}")
        print(f"  Ollama URL:     {settings.OLLAMA_BASE_URL}")
        print(f"  Generate model: {settings.OLLAMA_MODEL_GENERATE}")
        print(f"  Evaluate model: {settings.OLLAMA_MODEL_EVALUATE}")
        print()
        print("  Contents:")
        for status, cnt in content_stats.items():
            print(f"    {status:12s}: {cnt}")
        if not content_stats:
            print("    (none)")
        print()
        print("  Topics:")
        for status, cnt in topic_stats.items():
            print(f"    {status:12s}: {cnt}")
        if not topic_stats:
            print("    (none)")
        print()
        print(f"  Quality (7d):   avg={avg_quality}  evaluations={quality_count}")
        print("==============================\n")
    finally:
        await db.close()


async def cmd_pipeline() -> None:
    """Brain デュアル言語パイプラインを1回実行して終了する."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    components = await _init_full_components()
    db = components["db"]
    brain = components["brain"]

    try:
        logger.info("pipeline.start")
        result = await brain.run_dual_language_pipeline()
        logger.info("pipeline.done", result=result)
        print("\n--- Pipeline Result ---")
        if isinstance(result, dict):
            for key, value in result.items():
                try:
                    print(f"  {key}: {value}")
                except UnicodeEncodeError:
                    print(f"  {key}: {str(value).encode('utf-8', errors='replace').decode('utf-8')}")
        else:
            try:
                print(f"  {result}")
            except UnicodeEncodeError:
                print(f"  {str(result).encode('utf-8', errors='replace').decode('utf-8')}")
        print("-----------------------\n")
    finally:
        await db.close()


async def cmd_voice() -> None:
    """音声未生成の最新公開コンテンツに音声を生成する."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    components = await _init_full_components()
    db = components["db"]
    voice_engine = components["voice_engine"]

    try:
        logger.info("voice.start")
        conn = await db._get_connection()
        cursor = await conn.execute(
            """SELECT id, title, body, language, metadata FROM contents
               WHERE status = 'published'
                 AND (metadata IS NULL OR json_extract(metadata, '$.audio_path') IS NULL)
               ORDER BY created_at DESC""",
        )
        rows = await cursor.fetchall()

        if not rows:
            print("音声未生成のコンテンツはありません。")
            return

        import json as _json
        print(f"\n音声未生成コンテンツ: {len(rows)} 件")
        generated = 0
        for row in rows:
            try:
                audio_path = await voice_engine.synthesize_podcast(
                    title=row["title"],
                    body=row["body"],
                    language=row["language"],
                )
                if audio_path:
                    existing = _json.loads(row["metadata"]) if row["metadata"] else {}
                    existing["audio_path"] = str(audio_path)
                    await conn.execute(
                        "UPDATE contents SET metadata = ? WHERE id = ?",
                        (_json.dumps(existing, ensure_ascii=False), row["id"]),
                    )
                    await conn.commit()
                    generated += 1
                    print(f"  [OK] {row['title']} -> {audio_path}")
            except Exception as exc:
                print(f"  [NG] {row['title']}: {exc}")

        print(f"\n生成完了: {generated}/{len(rows)} 件")
        logger.info("voice.done", generated=generated, total=len(rows))
    finally:
        await db.close()


async def cmd_trends() -> None:
    """トレンド分析とコンテンツカレンダーを表示する."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    components = await _init_full_components()
    db = components["db"]
    trend_analyzer = components["trend_analyzer"]

    try:
        logger.info("trends.start")
        print("\n=== Trend Analysis & Content Calendar ===\n")

        for lang in ("ja", "en"):
            label = "日本語" if lang == "ja" else "English"
            print(f"--- {label} ({lang}) ---")
            predictions = await trend_analyzer.predict_next_topics(lang)
            if predictions:
                for i, topic in enumerate(predictions, 1):
                    if isinstance(topic, dict):
                        print(f"  {i}. {topic.get('title', topic)}")
                    else:
                        print(f"  {i}. {topic}")
            else:
                print("  (予測トピックなし)")
            print()

        print("==========================================\n")
        logger.info("trends.done")
    finally:
        await db.close()


async def cmd_publish() -> None:
    """最新コンテンツをサイトに公開する."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
    components = await _init_full_components()
    db = components["db"]
    publisher = components["publisher"]

    try:
        logger.info("publish.start")
        conn = await db._get_connection()
        cursor = await conn.execute(
            """SELECT id, title, language, metadata FROM contents
               WHERE status = 'published'
               ORDER BY created_at DESC LIMIT 10""",
        )
        rows = await cursor.fetchall()

        if not rows:
            print("公開対象のコンテンツはありません。")
            return

        print(f"\n公開対象コンテンツ: {len(rows)} 件\n")
        published = 0
        for row in rows:
            try:
                result = await publisher.publish_episode(
                    content_id=row["id"],
                )
                if result:
                    ep_num = await publisher.get_next_episode_number() - 1
                    issues = await publisher.validate_publish(ep_num)
                    status_mark = "OK" if not issues else "WARN"
                    print(f"  [{status_mark}] {row['title']}")
                    published += 1
                else:
                    print(f"  [SKIP] {row['title']}")
            except Exception as exc:
                print(f"  [NG] {row['title']}: {exc}")

        print(f"\n公開完了: {published}/{len(rows)} 件")
        logger.info("publish.done", published=published, total=len(rows))
    finally:
        await db.close()


async def cmd_init() -> None:
    """DB 初期化のみ."""
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    from core.database import DatabaseManager

    db = DatabaseManager()
    await db.init_db()
    await db.close()
    print("Database initialized successfully.")


# ---------------------------------------------------------------------------
# argparse
# ---------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    """CLI パーサーを構築する."""
    parser = argparse.ArgumentParser(
        prog="deepcast",
        description="Deepcast Engine — Autonomous AI Content Generation System",
    )
    sub = parser.add_subparsers(dest="command")
    sub.default = "serve"

    # serve
    serve_p = sub.add_parser("serve", help="Start FastAPI server + scheduler")
    serve_p.add_argument("--port", type=int, default=8000, help="Server port (default: 8000)")
    serve_p.add_argument("--host", type=str, default="0.0.0.0", help="Server host (default: 0.0.0.0)")
    serve_p.add_argument(
        "--no-scheduler",
        action="store_true",
        default=False,
        help="Start API without the background scheduler",
    )

    # generate
    sub.add_parser("generate", help="Run a single generation cycle and exit")

    # status
    sub.add_parser("status", help="Print system status and exit")

    # init
    sub.add_parser("init", help="Initialize database only")

    # pipeline
    sub.add_parser("pipeline", help="Run Brain dual-language pipeline once and exit")

    # voice
    sub.add_parser("voice", help="Generate voice for latest unpublished audio content")

    # trends
    sub.add_parser("trends", help="Show trend analysis and content calendar")

    # publish
    sub.add_parser("publish", help="Publish latest content to the website")

    return parser


# ---------------------------------------------------------------------------
# main
# ---------------------------------------------------------------------------


def main() -> None:
    """エントリーポイント."""
    parser = build_parser()
    args = parser.parse_args()

    command = args.command or "serve"

    if command == "serve":
        asyncio.run(
            cmd_serve(
                host=args.host,
                port=args.port,
                no_scheduler=args.no_scheduler,
            )
        )
    elif command == "generate":
        asyncio.run(cmd_generate())
    elif command == "status":
        asyncio.run(cmd_status())
    elif command == "init":
        asyncio.run(cmd_init())
    elif command == "pipeline":
        asyncio.run(cmd_pipeline())
    elif command == "voice":
        asyncio.run(cmd_voice())
    elif command == "trends":
        asyncio.run(cmd_trends())
    elif command == "publish":
        asyncio.run(cmd_publish())
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()

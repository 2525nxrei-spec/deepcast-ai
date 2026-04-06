"""DeepCast AI — 自律型エピソード生成・公開パイプライン (Autopilot).

人間の介入なしで以下を自動実行する:
  1. トレンド分析 → トピック選定 → 台本生成 → 品質評価 (Brain pipeline)
  2. 音声生成 (Gemini TTS / 3分構成)
  3. サイト公開 (HTML/JSON/RSS/sitemap)
  4. R2アップロード (wrangler CLI)
  5. Git commit & push (Cloudflare Pages自動デプロイ)

Usage:
    python autopilot.py              # 1サイクル実行（日本語のみ）
    python autopilot.py --both       # 日英両方
    python autopilot.py --dry-run    # テスト実行（公開・アップロード・pushしない）
    python autopilot.py --count 2    # 2エピソード生成
"""

from __future__ import annotations

import argparse
import asyncio
import io
import json
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import structlog

# engine/ からの相対インポートのためパスを追加
sys.path.insert(0, str(Path(__file__).parent))

from config.settings import settings

# structlog 設定
import logging

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
        logging.INFO,
    ),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("deepcast.autopilot")

JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# 初期化
# ---------------------------------------------------------------------------

async def _init_all():
    """全コンポーネントを初期化して返す."""
    from core.database import DatabaseManager
    from core.llm_client import LLMClient
    from engine.evaluator import ContentEvaluator
    from engine.generator import ContentGenerator
    from engine.self_manager import SelfManager
    from core.brain import Brain
    from core.voice_engine import VoiceEngine
    from manager.publisher import Publisher

    db = DatabaseManager()
    await db.init_db()

    llm = LLMClient()
    generator = ContentGenerator(llm_client=llm, db=db)
    evaluator = ContentEvaluator(llm=llm, db=db)
    brain = Brain(db=db, llm=llm, generator=generator, evaluator=evaluator)
    voice_engine = VoiceEngine()
    publisher = Publisher(db=db)

    return {
        "db": db,
        "brain": brain,
        "voice_engine": voice_engine,
        "publisher": publisher,
    }


# ---------------------------------------------------------------------------
# メインパイプライン
# ---------------------------------------------------------------------------

async def run_autopilot(
    language: str = "ja",
    dry_run: bool = False,
    episode_count: int = 1,
) -> dict:
    """自律パイプラインを1サイクル実行する.

    Returns:
        実行結果のサマリーdict.
    """
    start_time = time.time()
    results = {
        "language": language,
        "dry_run": dry_run,
        "episodes": [],
        "errors": [],
    }

    logger.info(
        "autopilot.start",
        language=language,
        dry_run=dry_run,
        episode_count=episode_count,
    )

    components = await _init_all()
    db = components["db"]
    brain = components["brain"]
    voice_engine = components["voice_engine"]
    publisher = components["publisher"]

    try:
        # ======================================================
        # Step 1: コンテンツ生成 (Brain pipeline)
        # ======================================================
        logger.info("autopilot.step1.content_generation")
        pipeline_results = await brain.run_pipeline(language)

        if not pipeline_results:
            logger.warning("autopilot.no_content_generated")
            results["errors"].append("コンテンツ生成失敗: パイプラインが空の結果を返しました")
            return results

        # 公開されたコンテンツのみ取得
        published = [r for r in pipeline_results if r.get("final_status") == "published"]
        if not published:
            logger.warning("autopilot.no_published_content")
            results["errors"].append("品質基準を満たすコンテンツが生成されませんでした")
            return results

        # episode_count 分だけ処理
        target_episodes = published[:episode_count]
        logger.info(
            "autopilot.content_ready",
            total_generated=len(pipeline_results),
            published=len(published),
            target=len(target_episodes),
        )

        for ep_data in target_episodes:
            content_id = ep_data.get("content_id")
            title = ep_data.get("title", "Untitled")
            episode_result = {
                "content_id": content_id,
                "title": title,
                "steps": {},
            }

            try:
                # ======================================================
                # Step 2: 音声生成
                # ======================================================
                logger.info("autopilot.step2.voice_generation", title=title)

                # DBからコンテンツ本文を取得
                content = await db.get_content(content_id)
                if not content:
                    raise RuntimeError(f"Content ID {content_id} not found in DB")

                audio_path = await voice_engine.synthesize_podcast(
                    title=content["title"],
                    body=content["body"],
                    language=content.get("language", "ja"),
                )

                # 音声長を記録
                duration_sec = await voice_engine._get_audio_duration(audio_path)
                episode_result["steps"]["voice"] = {
                    "status": "ok",
                    "path": str(audio_path),
                    "duration": duration_sec,
                }

                # metadata に audio_path を保存
                conn = await db._get_connection()
                existing_meta = content.get("metadata")
                meta = json.loads(existing_meta) if isinstance(existing_meta, str) and existing_meta else (existing_meta or {})
                meta["audio_path"] = str(audio_path)
                if duration_sec:
                    minutes = int(duration_sec // 60)
                    seconds = int(duration_sec % 60)
                    meta["duration"] = f"{minutes}:{seconds:02d}"
                await conn.execute(
                    "UPDATE contents SET metadata = ? WHERE id = ?",
                    (json.dumps(meta, ensure_ascii=False), content_id),
                )
                await conn.commit()

                logger.info(
                    "autopilot.voice.done",
                    path=str(audio_path),
                    duration=duration_sec,
                )

                if dry_run:
                    episode_result["steps"]["publish"] = {"status": "skipped (dry-run)"}
                    episode_result["steps"]["r2"] = {"status": "skipped (dry-run)"}
                    episode_result["steps"]["git"] = {"status": "skipped (dry-run)"}
                    results["episodes"].append(episode_result)
                    continue

                # ======================================================
                # Step 3: サイト公開
                # ======================================================
                logger.info("autopilot.step3.publish", title=title)
                # autopilot内ではAUTO_GIT_PUSHを一時的にTrueにする
                # （publisherのgit_stage_and_commitが動作するように）
                original_auto_git = settings.AUTO_GIT_PUSH
                settings.AUTO_GIT_PUSH = True
                publish_results = await publisher.publish_episode(content_id)
                all_ok = all(r.success for r in publish_results)
                episode_result["steps"]["publish"] = {
                    "status": "ok" if all_ok else "partial",
                    "details": [
                        {"target": r.target.value, "success": r.success, "error": r.error}
                        for r in publish_results
                    ],
                }

                if not all_ok:
                    logger.warning("autopilot.publish.partial_failure", title=title)

                # ======================================================
                # Step 4: R2アップロード
                # ======================================================
                logger.info("autopilot.step4.r2_upload", title=title)
                ep_number = await publisher.get_next_episode_number() - 1
                remote_key = f"episodes/ep{ep_number:03d}.mp3"

                r2_ok = await publisher.upload_to_r2(
                    local_path=str(audio_path),
                    remote_key=remote_key,
                )
                episode_result["steps"]["r2"] = {
                    "status": "ok" if r2_ok else "failed",
                    "remote_key": remote_key,
                    "public_url": f"{settings.R2_PUBLIC_URL}/{remote_key}" if r2_ok else None,
                }

                if not r2_ok:
                    logger.error("autopilot.r2.failed", title=title)
                    results["errors"].append(f"R2アップロード失敗: {title}")

                # ======================================================
                # Step 5: Git push
                # ======================================================
                logger.info("autopilot.step5.git_push")
                push_ok = await publisher.git_push()
                episode_result["steps"]["git"] = {
                    "status": "ok" if push_ok else "skipped",
                }

                # AUTO_GIT_PUSHを元に戻す
                settings.AUTO_GIT_PUSH = original_auto_git

            except Exception as exc:
                logger.exception("autopilot.episode.error", title=title)
                episode_result["steps"]["error"] = str(exc)
                results["errors"].append(f"{title}: {exc}")

            results["episodes"].append(episode_result)

    except Exception as exc:
        logger.exception("autopilot.fatal_error")
        results["errors"].append(f"致命的エラー: {exc}")
    finally:
        await db.close()

    elapsed = time.time() - start_time
    results["elapsed_seconds"] = round(elapsed, 1)
    results["completed_at"] = datetime.now(JST).isoformat()

    logger.info(
        "autopilot.done",
        episodes=len(results["episodes"]),
        errors=len(results["errors"]),
        elapsed=results["elapsed_seconds"],
    )

    return results


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def _print_results(results: dict) -> None:
    """結果を見やすく表示する."""
    print("\n" + "=" * 60)
    print("  DeepCast AI Autopilot — 実行結果")
    print("=" * 60)
    print(f"  言語: {results['language']}")
    print(f"  ドライラン: {results['dry_run']}")
    print(f"  処理時間: {results.get('elapsed_seconds', '?')}秒")
    print(f"  完了時刻: {results.get('completed_at', '?')}")
    print()

    for i, ep in enumerate(results.get("episodes", []), 1):
        print(f"  --- エピソード {i} ---")
        print(f"  タイトル: {ep.get('title', '?')}")
        print(f"  Content ID: {ep.get('content_id', '?')}")
        for step_name, step_data in ep.get("steps", {}).items():
            if isinstance(step_data, dict):
                status = step_data.get("status", "?")
                print(f"    {step_name}: {status}")
                if step_name == "voice" and step_data.get("duration"):
                    print(f"      音声長: {step_data['duration']:.1f}秒")
                if step_name == "r2" and step_data.get("public_url"):
                    print(f"      URL: {step_data['public_url']}")
            else:
                print(f"    {step_name}: {step_data}")
        print()

    if results.get("errors"):
        print("  [エラー]")
        for err in results["errors"]:
            print(f"    - {err}")
        print()

    print("=" * 60 + "\n")


async def main() -> None:
    """CLIエントリーポイント."""
    parser = argparse.ArgumentParser(
        description="DeepCast AI Autopilot — 自律エピソード生成・公開",
    )
    parser.add_argument(
        "--both", action="store_true",
        help="日英両方のエピソードを生成",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="テスト実行（公開・アップロード・pushしない）",
    )
    parser.add_argument(
        "--count", type=int, default=1,
        help="1回あたりの生成エピソード数（デフォルト: 1）",
    )
    parser.add_argument(
        "--lang", type=str, default="ja",
        choices=["ja", "en"],
        help="言語（--both未指定時のみ有効）",
    )
    args = parser.parse_args()

    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")

    if args.both:
        for lang in ("ja", "en"):
            results = await run_autopilot(
                language=lang,
                dry_run=args.dry_run,
                episode_count=args.count,
            )
            _print_results(results)
    else:
        results = await run_autopilot(
            language=args.lang,
            dry_run=args.dry_run,
            episode_count=args.count,
        )
        _print_results(results)


if __name__ == "__main__":
    asyncio.run(main())

"""Deepcast Engine — 自律的自己改善マネージャー.

コンテンツ生成サイクルの自動運用、品質分析、プロンプト最適化を担う。
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

import structlog

from config.settings import settings
from core.database import DatabaseManager
from core.llm_client import LLMClient
from engine.evaluator import ContentEvaluator
from engine.generator import ContentGenerator
from manager.publisher import Publisher

logger = structlog.get_logger(__name__)

PROMPTS_PATH = Path(__file__).resolve().parent.parent / "config" / "prompts.json"


class SelfManager:
    """自律的にコンテンツ生成・品質改善サイクルを回すマネージャー."""

    def __init__(
        self,
        db: DatabaseManager,
        llm: LLMClient,
        generator: ContentGenerator,
        evaluator: ContentEvaluator,
    ) -> None:
        self.db = db
        self.llm = llm
        self.generator = generator
        self.evaluator = evaluator
        self._prompts: dict[str, Any] = self._load_prompts()

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _load_prompts(self) -> dict[str, Any]:
        """config/prompts.json を読み込む."""
        try:
            with open(PROMPTS_PATH, encoding="utf-8") as f:
                return json.load(f)
        except (FileNotFoundError, json.JSONDecodeError) as exc:
            logger.error("prompts.json の読み込みに失敗", error=str(exc))
            return {}

    def _save_prompts(self, prompts: dict[str, Any]) -> None:
        """config/prompts.json を上書き保存する."""
        with open(PROMPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)
        self._prompts = prompts
        logger.info("prompts.json を更新しました")

    # ------------------------------------------------------------------
    # 1. analyze_performance
    # ------------------------------------------------------------------

    async def analyze_performance(self, language: str) -> dict:
        """直近 7 日間の品質ログを分析し、パフォーマンス指標を返す.

        Returns:
            dict with keys: avg_score, best_category, worst_category,
            total_generated, total_published, rejection_rate
        """
        since = (datetime.now(timezone.utc) - timedelta(days=7)).isoformat()

        rows = await self.db.fetch_all(
            """
            SELECT c.category, ql.score, c.status
            FROM quality_logs ql
            JOIN contents c ON c.id = ql.content_id
            WHERE c.language = ? AND ql.created_at >= ?
            """,
            (language, since),
        )

        if not rows:
            logger.info("分析対象のログなし", language=language)
            return {
                "avg_score": 0.0,
                "best_category": None,
                "worst_category": None,
                "total_generated": 0,
                "total_published": 0,
                "rejection_rate": 0.0,
            }

        total_generated = len(rows)
        total_published = sum(1 for r in rows if r["status"] == "published")
        scores = [r["score"] for r in rows]
        avg_score = sum(scores) / total_generated

        # カテゴリ別の平均スコアを算出
        cat_scores: dict[str, list[float]] = {}
        for r in rows:
            cat_scores.setdefault(r["category"] or "unknown", []).append(r["score"])
        cat_avg = {c: sum(s) / len(s) for c, s in cat_scores.items()}

        best_category = max(cat_avg, key=cat_avg.get)  # type: ignore[arg-type]
        worst_category = min(cat_avg, key=cat_avg.get)  # type: ignore[arg-type]

        rejection_rate = (
            (total_generated - total_published) / total_generated
            if total_generated
            else 0.0
        )

        analysis = {
            "avg_score": round(avg_score, 2),
            "best_category": best_category,
            "worst_category": worst_category,
            "total_generated": total_generated,
            "total_published": total_published,
            "rejection_rate": round(rejection_rate, 4),
        }

        logger.info("パフォーマンス分析完了", language=language, **analysis)
        return analysis

    # ------------------------------------------------------------------
    # 2. optimize_prompts
    # ------------------------------------------------------------------

    async def optimize_prompts(self, language: str) -> bool:
        """品質トレンドが低下している場合、LLM でプロンプトを改善する.

        Returns:
            True if prompts were updated, False otherwise.
        """
        # 直近 7 日 vs その前 7 日を比較
        now = datetime.now(timezone.utc)
        recent_since = (now - timedelta(days=7)).isoformat()
        prev_since = (now - timedelta(days=14)).isoformat()
        recent_until = now.isoformat()
        prev_until = (now - timedelta(days=7)).isoformat()

        recent_rows = await self.db.fetch_all(
            """SELECT ql.score FROM quality_logs ql
               JOIN contents c ON c.id = ql.content_id
               WHERE c.language = ? AND ql.created_at >= ? AND ql.created_at < ?""",
            (language, recent_since, recent_until),
        )
        prev_rows = await self.db.fetch_all(
            """SELECT ql.score FROM quality_logs ql
               JOIN contents c ON c.id = ql.content_id
               WHERE c.language = ? AND ql.created_at >= ? AND ql.created_at < ?""",
            (language, prev_since, prev_until),
        )

        if not recent_rows or not prev_rows:
            logger.info("最適化に十分なデータがありません", language=language)
            return False

        recent_avg = sum(r["score"] for r in recent_rows) / len(recent_rows)
        prev_avg = sum(r["score"] for r in prev_rows) / len(prev_rows)

        if recent_avg >= prev_avg:
            logger.info(
                "品質トレンドは安定または向上中",
                language=language,
                recent_avg=round(recent_avg, 2),
                prev_avg=round(prev_avg, 2),
            )
            return False

        logger.warning(
            "品質トレンド低下を検出 — プロンプト最適化を開始",
            language=language,
            recent_avg=round(recent_avg, 2),
            prev_avg=round(prev_avg, 2),
        )

        # 低スコアコンテンツのフィードバックを収集
        low_score_rows = await self.db.fetch_all(
            """
            SELECT ql.feedback FROM quality_logs ql
            JOIN contents c ON c.id = ql.content_id
            WHERE c.language = ? AND ql.created_at >= ? AND ql.score < ?
            ORDER BY ql.score ASC LIMIT 5
            """,
            (language, recent_since, settings.QUALITY_THRESHOLD),
        )
        feedbacks = [r["feedback"] for r in low_score_rows if r.get("feedback")]

        # 現行プロンプト
        prompt_key = f"{language}_generate"
        current_prompt = self._prompts.get(prompt_key, {}).get("content", "")

        # LLM にプロンプト改善を依頼
        improvement_request = (
            "以下は現在のコンテンツ生成プロンプトと、最近の低評価コンテンツへのフィードバックです。\n"
            "フィードバックを踏まえ、改善されたシステムプロンプトを生成してください。\n"
            "改善プロンプトのみを出力してください。余計な説明は不要です。\n\n"
            f"【現行プロンプト】\n{current_prompt}\n\n"
            f"【低評価フィードバック】\n" + "\n---\n".join(feedbacks)
        )

        new_prompt_text = await self.llm.generate(
            prompt=improvement_request,
            system_prompt="You are an expert prompt engineer. Output only the improved prompt.",
        )

        if not new_prompt_text or not new_prompt_text.strip():
            logger.error("LLM から有効な改善プロンプトを取得できませんでした")
            return False

        # 旧プロンプトを prompt_history テーブルに保存
        await self.db.execute(
            """
            INSERT INTO prompt_history (prompt_type, prompt_text)
            VALUES (?, ?)
            """,
            (prompt_key, current_prompt),
        )

        # prompts.json を更新
        import copy
        updated_prompts = copy.deepcopy(self._prompts)
        updated_prompts[prompt_key]["content"] = new_prompt_text.strip()
        self._save_prompts(updated_prompts)

        logger.info("プロンプト最適化完了", language=language, prompt_key=prompt_key)
        return True

    # ------------------------------------------------------------------
    # 3. select_next_topic
    # ------------------------------------------------------------------

    async def select_next_topic(self, language: str) -> dict | None:
        """次に生成すべきトピックを選定する.

        優先ロジック:
        1. DB の pending トピックを確認
        2. なければ generator.research_topics() で新規調査
        3. カテゴリ多様性 / 新しさ / キーワード需要でスコアリング

        Returns:
            選定されたトピック dict、または None。
        """
        # 1. pending トピックを取得
        pending = await self.db.fetch_all(
            """
            SELECT * FROM topics
            WHERE language = ? AND status = 'pending'
            ORDER BY created_at ASC
            """,
            (language,),
        )

        # 2. pending がなければリサーチ
        if not pending:
            logger.info("pending トピックなし — 新規リサーチ実行", language=language)
            new_topics = await self.generator.research_topics(language)
            if not new_topics:
                logger.warning("トピックリサーチ結果なし", language=language)
                return None
            # TopicIdea を dict に変換して統一
            pending = [t.model_dump() if hasattr(t, "model_dump") else t for t in new_topics]

        # 3. 直近の生成カテゴリを取得し多様性スコアを算出
        recent_categories = await self.db.fetch_all(
            """
            SELECT c.category FROM quality_logs ql
            JOIN contents c ON c.id = ql.content_id
            WHERE c.language = ?
            ORDER BY ql.created_at DESC LIMIT 10
            """,
            (language,),
        )
        recent_cat_list = [r["category"] for r in recent_categories]

        def _priority_score(topic: dict) -> float:
            """トピック優先度を算出（高い方が優先）."""
            score = 0.0

            # カテゴリ多様性: 最近使われていないカテゴリを優遇
            cat = topic.get("category", "")
            if cat not in recent_cat_list:
                score += 10.0
            else:
                # 最近使われた回数に応じて減点
                score -= recent_cat_list.count(cat) * 2.0

            # キーワード数が多いほど需要があると推定
            keywords = topic.get("keywords", [])
            score += len(keywords) * 1.5

            # 難易度が低いトピックを優遇
            difficulty = topic.get("difficulty", "medium")
            difficulty_bonus = {"low": 5.0, "medium": 2.0, "high": 0.0}
            score += difficulty_bonus.get(difficulty, 2.0)

            return score

        # スコア降順でソートし最優先トピックを返す
        ranked = sorted(pending, key=_priority_score, reverse=True)
        selected = ranked[0]

        logger.info(
            "トピック選定完了",
            language=language,
            title=selected.get("title", "N/A"),
        )
        return selected

    # ------------------------------------------------------------------
    # 4. run_autonomous_cycle
    # ------------------------------------------------------------------

    async def run_autonomous_cycle(self, language: str) -> dict:
        """1 言語分の自律生成サイクルを実行する.

        select_topic -> generate -> evaluate -> store

        Returns:
            dict with keys: topic, score, status, content_id
        """
        cycle_start = datetime.now(timezone.utc)
        result: dict[str, Any] = {
            "topic": None,
            "score": 0,
            "status": "error",
            "content_id": None,
        }

        try:
            # 1. トピック選定
            topic = await self.select_next_topic(language)
            if topic is None:
                logger.warning("トピックが見つかりません — サイクル中断", language=language)
                await self._log_system("cycle_skip", language, "トピックなし")
                return result

            result["topic"] = topic.get("title", "unknown")

            # 2. コンテンツ生成
            logger.info("コンテンツ生成開始", language=language, topic=result["topic"])
            from engine.generator import TopicIdea
            # DB の topics テーブルには target_audience / angle がないためデフォルト補完
            topic_data = dict(topic) if isinstance(topic, dict) else topic
            # keywords might be stored as JSON string in DB
            kw = topic_data.get("keywords", [])
            if isinstance(kw, str):
                try:
                    kw = json.loads(kw)
                except (ValueError, TypeError):
                    kw = [kw]
            topic_idea = TopicIdea(
                title=topic_data.get("title", ""),
                category=topic_data.get("category", "general"),
                keywords=kw if isinstance(kw, list) else [],
                target_audience=topic_data.get("target_audience", "general audience"),
                angle=topic_data.get("angle", "informative overview"),
            )
            content = await self.generator.generate_content(topic_idea, language)

            if not content:
                logger.error("コンテンツ生成失敗", language=language)
                await self._log_system("generate_fail", language, result["topic"])
                return result

            # 3. 品質評価
            evaluation = await self.evaluator.evaluate(
                content_title=content.title,
                content_body=content.body,
                language=language,
            )
            score = evaluation.overall_score
            result["score"] = score

            # 4. 閾値判定 & 保存
            status = "published" if score >= settings.QUALITY_THRESHOLD else "rejected"
            content_id = await self.db.save_content(
                title=content.title,
                body=content.body,
                language=language,
                category=content.category,
                tags=content.tags,
                quality_score=score,
                status=status,
                topic_source=topic.get("title", ""),
            )

            result["status"] = status
            result["content_id"] = content_id

            # 公開処理: サイトファイル生成
            if status == "published":
                publisher = Publisher(db=self.db)
                await publisher.publish_episode(content_id)

            # 品質ログ記録
            await self.db.save_quality_log(
                content_id=content_id,
                score=score,
                feedback=evaluation.feedback,
                evaluator_model="gemini-2.5-flash",
            )

            elapsed = (datetime.now(timezone.utc) - cycle_start).total_seconds()
            logger.info(
                "自律サイクル完了",
                language=language,
                topic=result["topic"],
                score=score,
                status=status,
                elapsed_sec=round(elapsed, 1),
            )

            await self._log_system(
                "cycle_complete",
                language,
                f"topic={result['topic']} score={score} status={status}",
            )

        except Exception:
            logger.exception("自律サイクルで予期しないエラー", language=language)
            await self._log_system("cycle_error", language, "unexpected exception")

        return result

    # ------------------------------------------------------------------
    # 5. run_full_cycle
    # ------------------------------------------------------------------

    async def run_full_cycle(self) -> dict:
        """ja / en 両言語のサイクルを実行し、必要に応じてプロンプト最適化を行う.

        Returns:
            dict with keys: ja, en, prompt_optimized
        """
        results: dict[str, Any] = {
            "ja": {},
            "en": {},
            "prompt_optimized": {"ja": False, "en": False},
        }

        for lang in ("ja", "en"):
            results[lang] = await self.run_autonomous_cycle(lang)

        # プロンプト最適化チェック
        for lang in ("ja", "en"):
            try:
                optimized = await self.optimize_prompts(lang)
                results["prompt_optimized"][lang] = optimized
            except Exception:
                logger.exception("プロンプト最適化でエラー", language=lang)

        logger.info("フルサイクル完了", results=results)
        return results

    # ------------------------------------------------------------------
    # 6. get_status_report
    # ------------------------------------------------------------------

    async def get_status_report(self) -> str:
        """人間が読めるステータスレポートを生成する."""
        today_start = datetime.now(timezone.utc).replace(
            hour=0, minute=0, second=0, microsecond=0
        ).isoformat()

        lines: list[str] = []
        lines.append("=" * 50)
        lines.append("  Deepcast Engine — Status Report")
        lines.append(f"  Generated: {datetime.now(timezone.utc).strftime('%Y-%m-%d %H:%M UTC')}")
        lines.append("=" * 50)

        for lang in ("ja", "en"):
            label = "日本語" if lang == "ja" else "English"
            lines.append(f"\n--- {label} ({lang}) ---")

            # 今日の生成数
            today_rows = await self.db.fetch_all(
                """SELECT ql.score, c.status FROM quality_logs ql
                   JOIN contents c ON c.id = ql.content_id
                   WHERE c.language = ? AND ql.created_at >= ?""",
                (lang, today_start),
            )
            generated = len(today_rows)
            published = sum(1 for r in today_rows if r["status"] == "published")
            rejected = generated - published
            scores = [r["score"] for r in today_rows]
            avg_score = round(sum(scores) / len(scores), 1) if scores else 0.0

            lines.append(f"  今日の生成数: {generated}")
            lines.append(f"  公開: {published} / リジェクト: {rejected}")
            lines.append(f"  平均スコア: {avg_score}")

            # 7 日間分析
            perf = await self.analyze_performance(lang)
            lines.append(f"  7日間平均スコア: {perf['avg_score']}")
            lines.append(f"  最高カテゴリ: {perf['best_category'] or 'N/A'}")
            lines.append(f"  最低カテゴリ: {perf['worst_category'] or 'N/A'}")
            lines.append(f"  リジェクト率: {perf['rejection_rate'] * 100:.1f}%")

        # システムヘルス
        lines.append("\n--- System Health ---")
        try:
            error_rows = await self.db.fetch_all(
                "SELECT COUNT(*) as cnt FROM system_logs WHERE level = 'error' AND created_at >= ?",
                (today_start,),
            )
            error_count = error_rows[0]["cnt"] if error_rows else 0
            lines.append(f"  今日のエラー数: {error_count}")
        except Exception:
            lines.append("  今日のエラー数: 取得不可")

        lines.append(f"  品質閾値: {settings.QUALITY_THRESHOLD}")
        lines.append("  生成モデル: gemini-2.5-flash")
        lines.append("  評価モデル: gemini-2.5-flash")
        lines.append("=" * 50)

        report = "\n".join(lines)
        logger.info("ステータスレポート生成完了")
        return report

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    async def _log_system(self, event: str, language: str, detail: str) -> None:
        """system_logs テーブルにログを記録する."""
        try:
            await self.db.save_system_log(
                level="INFO",
                message=f"[{language}] {event}: {detail}",
                component="self_manager",
            )
        except Exception:
            logger.exception("system_logs への書き込みに失敗")

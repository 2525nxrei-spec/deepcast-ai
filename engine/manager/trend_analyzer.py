"""Deepcast Engine — 予測トレンド分析モジュール.

過去のコンテンツパフォーマンスと LLM を組み合わせ、
トピック予測・コンテンツギャップ分析・カレンダー生成を行う。
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta
from typing import Any

import structlog
from pydantic import BaseModel, field_validator

from config.settings import settings
from core.database import DatabaseManager
from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TrendSignal(BaseModel):
    """LLM が返すトレンドシグナル."""

    topic: str
    relevance_score: float  # 0-1
    category: str
    language: str
    reasoning: str
    keywords: list[str]
    suggested_angle: str
    urgency: str  # "high", "medium", "low"

    @field_validator("relevance_score")
    @classmethod
    def clamp_score(cls, v: float) -> float:
        return max(0.0, min(1.0, v))

    @field_validator("urgency")
    @classmethod
    def validate_urgency(cls, v: str) -> str:
        v = v.lower()
        if v not in ("high", "medium", "low"):
            return "medium"
        return v


class ContentPerformance(BaseModel):
    """カテゴリ別パフォーマンスサマリー."""

    category: str
    avg_score: float
    content_count: int
    trend: str  # "rising", "stable", "declining"

    @field_validator("trend")
    @classmethod
    def validate_trend(cls, v: str) -> str:
        v = v.lower()
        if v not in ("rising", "stable", "declining"):
            return "stable"
        return v


# ---------------------------------------------------------------------------
# Seasonal themes mapping
# ---------------------------------------------------------------------------

_JP_SEASONAL: dict[int, list[str]] = {
    1: ["新年の抱負", "年始ビジネス戦略", "初売りマーケティング"],
    2: ["バレンタインキャンペーン", "年度末準備", "確定申告"],
    3: ["年度末総括", "新生活準備", "桜シーズンマーケティング", "卒業・入学"],
    4: ["新年度スタート", "新入社員研修", "GW準備"],
    5: ["GWキャンペーン", "母の日", "梅雨対策ビジネス"],
    6: ["梅雨シーズン", "夏季ボーナス", "上半期振り返り"],
    7: ["夏季キャンペーン", "お中元", "夏休み計画"],
    8: ["お盆", "夏季休暇", "下半期戦略"],
    9: ["秋の新商品", "シルバーウィーク", "ハロウィン準備"],
    10: ["ハロウィン", "秋キャンペーン", "年末商戦準備"],
    11: ["ブラックフライデー", "年末商戦", "お歳暮準備"],
    12: ["年末総括", "クリスマスキャンペーン", "来年度計画"],
}

_EN_SEASONAL: dict[int, list[str]] = {
    1: ["New Year trends", "CES tech announcements", "annual planning"],
    2: ["Valentine marketing", "Q1 strategies", "AI industry updates"],
    3: ["SXSW trends", "spring campaigns", "end of Q1 review"],
    4: ["Earth Day sustainability", "spring product launches", "Q2 planning"],
    5: ["summer prep marketing", "Google I/O", "Memorial Day"],
    6: ["WWDC Apple updates", "mid-year review", "summer campaigns"],
    7: ["Amazon Prime Day", "summer trends", "back-to-school prep"],
    8: ["back-to-school", "fall planning", "late summer campaigns"],
    9: ["fall product launches", "IFA tech", "Q4 preparation"],
    10: ["Halloween marketing", "holiday season prep", "Black Friday strategy"],
    11: ["Black Friday", "Cyber Monday", "holiday campaigns"],
    12: ["year-end review", "Christmas campaigns", "next-year predictions"],
}

# ---------------------------------------------------------------------------
# TrendAnalyzer
# ---------------------------------------------------------------------------


class TrendAnalyzer:
    """コンテンツトレンド予測・分析エンジン."""

    def __init__(
        self,
        db: DatabaseManager | None = None,
        llm: LLMClient | None = None,
    ) -> None:
        self.db = db or DatabaseManager()
        self.llm = llm or LLMClient()

    # ------------------------------------------------------------------
    # 1. analyze_content_gaps
    # ------------------------------------------------------------------

    async def analyze_content_gaps(self, language: str) -> list[dict]:
        """公開済みコンテンツのカテゴリ分布を分析し、ギャップを返す.

        Returns:
            カテゴリごとの count / avg_score / gap_reason を含む dict のリスト。
        """
        logger.info("trend.analyze_content_gaps.start", language=language)

        # カテゴリ別の件数と平均スコア
        rows = await self.db.fetch_all(
            """
            SELECT category,
                   COUNT(*)                AS content_count,
                   ROUND(AVG(quality_score), 1) AS avg_score
              FROM contents
             WHERE language = ? AND status = 'published' AND category IS NOT NULL
             GROUP BY category
             ORDER BY content_count ASC
            """,
            (language,),
        )

        if not rows:
            logger.warning("trend.analyze_content_gaps.no_data", language=language)
            return []

        total = sum(r["content_count"] for r in rows)
        avg_count = total / len(rows) if rows else 0

        gaps: list[dict] = []
        for row in rows:
            gap_reason: str | None = None
            if row["content_count"] < avg_count * 0.5:
                gap_reason = "underrepresented"
            elif row["avg_score"] >= 80:
                gap_reason = "high_quality_low_volume"

            gaps.append(
                {
                    "category": row["category"],
                    "content_count": row["content_count"],
                    "avg_score": row["avg_score"],
                    "gap_reason": gap_reason,
                    "needs_more": gap_reason is not None,
                }
            )

        # needs_more を先頭に、件数昇順
        gaps.sort(key=lambda g: (not g["needs_more"], g["content_count"]))

        logger.info(
            "trend.analyze_content_gaps.done",
            language=language,
            total_categories=len(gaps),
            gaps_found=sum(1 for g in gaps if g["needs_more"]),
        )
        return gaps

    # ------------------------------------------------------------------
    # 2. predict_next_topics
    # ------------------------------------------------------------------

    async def predict_next_topics(
        self, language: str, count: int = 5
    ) -> list[TrendSignal]:
        """LLM を使い次に作るべきトピックを予測する.

        Returns:
            relevance_score 降順でソートされた TrendSignal のリスト。
        """
        logger.info(
            "trend.predict_next_topics.start",
            language=language,
            count=count,
        )

        # 材料を収集
        gaps = await self.analyze_content_gaps(language)
        seasonal = await self.get_seasonal_themes(language)

        # 過去の高スコアコンテンツ
        top_contents = await self.db.fetch_all(
            """
            SELECT title, category, quality_score
              FROM contents
             WHERE language = ? AND status = 'published'
             ORDER BY quality_score DESC
             LIMIT 20
            """,
            (language,),
        )

        today = date.today()
        month_name = today.strftime("%B")
        season_map = {
            1: "winter", 2: "winter", 3: "spring",
            4: "spring", 5: "spring", 6: "summer",
            7: "summer", 8: "summer", 9: "autumn",
            10: "autumn", 11: "autumn", 12: "winter",
        }
        current_season = season_map[today.month]

        prompt = f"""Analyze the following data and predict the {count} best topics to create next.

Language: {language}
Current date: {today.isoformat()}
Month: {month_name}
Season: {current_season}

Content gaps (categories needing more content):
{json.dumps(gaps, ensure_ascii=False, indent=2)}

Seasonal themes to consider:
{json.dumps(seasonal, ensure_ascii=False)}

Top performing past content:
{json.dumps(top_contents, ensure_ascii=False, indent=2)}

Return a JSON object with key "predictions" containing an array of exactly {count} objects.
Each object must have these fields:
- topic (string): specific topic title in {language}
- relevance_score (float 0-1): how relevant/timely this topic is
- category (string): content category
- language (string): "{language}"
- reasoning (string): why this topic should be created now
- keywords (array of strings): 3-5 relevant keywords
- suggested_angle (string): recommended approach/angle for the content
- urgency (string): "high", "medium", or "low"

Prioritize:
1. Topics that fill content gaps
2. Seasonally relevant topics for {month_name}
3. Categories with proven high quality scores
4. Diversity across categories"""

        system_prompt = (
            "You are a content strategy analyst. "
            "Return ONLY valid JSON. No markdown, no explanation."
        )

        result = await self.llm.generate_json(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.4,
        )

        predictions_raw: list[dict[str, Any]] = result.get("predictions", [])

        # Pydantic でバリデーション
        signals: list[TrendSignal] = []
        for item in predictions_raw:
            try:
                signal = TrendSignal(**item)
                signals.append(signal)
            except Exception as exc:
                logger.warning(
                    "trend.predict.validation_failed",
                    item=item,
                    error=str(exc),
                )

        # relevance_score 降順
        signals.sort(key=lambda s: s.relevance_score, reverse=True)

        # DB の topics テーブルに保存
        for signal in signals:
            priority = {"high": 3, "medium": 2, "low": 1}.get(signal.urgency, 1)
            await self.db.save_topic(
                title=signal.topic,
                language=signal.language,
                category=signal.category,
                keywords=signal.keywords,
                priority=priority,
            )

        logger.info(
            "trend.predict_next_topics.done",
            language=language,
            predicted=len(signals),
        )
        return signals

    # ------------------------------------------------------------------
    # 3. analyze_performance_patterns
    # ------------------------------------------------------------------

    async def analyze_performance_patterns(
        self, language: str, days: int = 30
    ) -> dict:
        """指定期間のコンテンツパフォーマンスパターンを分析する.

        Returns:
            best_categories, score_distribution, optimal_length, patterns を含む dict。
        """
        logger.info(
            "trend.analyze_performance_patterns.start",
            language=language,
            days=days,
        )

        # カテゴリ別パフォーマンス
        category_perf = await self.db.fetch_all(
            """
            SELECT c.category,
                   ROUND(AVG(ql.score), 1) AS avg_score,
                   COUNT(DISTINCT c.id)    AS content_count
              FROM quality_logs ql
              JOIN contents c ON c.id = ql.content_id
             WHERE c.language = ?
               AND ql.created_at >= DATE('now', ?)
               AND c.category IS NOT NULL
             GROUP BY c.category
             ORDER BY avg_score DESC
            """,
            (language, f"-{days} days"),
        )

        # スコア分布
        score_dist = await self.db.fetch_all(
            """
            SELECT CASE
                     WHEN ql.score >= 90 THEN 'excellent'
                     WHEN ql.score >= 80 THEN 'good'
                     WHEN ql.score >= 60 THEN 'average'
                     ELSE 'needs_improvement'
                   END AS tier,
                   COUNT(*) AS count
              FROM quality_logs ql
              JOIN contents c ON c.id = ql.content_id
             WHERE c.language = ?
               AND ql.created_at >= DATE('now', ?)
             GROUP BY tier
             ORDER BY count DESC
            """,
            (language, f"-{days} days"),
        )

        # コンテンツ長とスコアの関係
        length_analysis = await self.db.fetch_all(
            """
            SELECT CASE
                     WHEN LENGTH(c.body) < 1000  THEN 'short'
                     WHEN LENGTH(c.body) < 3000  THEN 'medium'
                     ELSE 'long'
                   END AS length_tier,
                   ROUND(AVG(ql.score), 1)    AS avg_score,
                   COUNT(DISTINCT c.id)       AS content_count
              FROM quality_logs ql
              JOIN contents c ON c.id = ql.content_id
             WHERE c.language = ?
               AND ql.created_at >= DATE('now', ?)
             GROUP BY length_tier
            """,
            (language, f"-{days} days"),
        )

        # トレンド判定 (カテゴリ別)
        performances: list[dict] = []
        for row in category_perf:
            # 前半/後半でスコアを比較してトレンド判定
            midpoint = days // 2
            recent = await self.db.fetch_all(
                """
                SELECT ROUND(AVG(ql.score), 1) AS avg
                  FROM quality_logs ql
                  JOIN contents c ON c.id = ql.content_id
                 WHERE c.language = ? AND c.category = ?
                   AND ql.created_at >= DATE('now', ?)
                """,
                (language, row["category"], f"-{midpoint} days"),
            )
            older = await self.db.fetch_all(
                """
                SELECT ROUND(AVG(ql.score), 1) AS avg
                  FROM quality_logs ql
                  JOIN contents c ON c.id = ql.content_id
                 WHERE c.language = ? AND c.category = ?
                   AND ql.created_at >= DATE('now', ?)
                   AND ql.created_at < DATE('now', ?)
                """,
                (language, row["category"], f"-{days} days", f"-{midpoint} days"),
            )

            recent_avg = (recent[0]["avg"] or 0) if recent else 0
            older_avg = (older[0]["avg"] or 0) if older else 0

            if recent_avg > older_avg + 5:
                trend = "rising"
            elif recent_avg < older_avg - 5:
                trend = "declining"
            else:
                trend = "stable"

            performances.append(
                {
                    "category": row["category"],
                    "avg_score": row["avg_score"],
                    "content_count": row["content_count"],
                    "trend": trend,
                }
            )

        # 最適なコンテンツ長を特定
        optimal_length = "medium"
        if length_analysis:
            best_tier = max(length_analysis, key=lambda x: x["avg_score"] or 0)
            optimal_length = best_tier["length_tier"]

        analysis = {
            "period_days": days,
            "language": language,
            "best_categories": performances[:5],
            "score_distribution": score_dist,
            "optimal_content_length": optimal_length,
            "length_analysis": length_analysis,
            "total_evaluated": sum(r["content_count"] for r in category_perf),
            "patterns": {
                "rising_categories": [
                    p["category"] for p in performances if p["trend"] == "rising"
                ],
                "declining_categories": [
                    p["category"] for p in performances if p["trend"] == "declining"
                ],
            },
        }

        logger.info(
            "trend.analyze_performance_patterns.done",
            language=language,
            categories_analyzed=len(performances),
        )
        return analysis

    # ------------------------------------------------------------------
    # 4. generate_content_calendar
    # ------------------------------------------------------------------

    async def generate_content_calendar(
        self, language: str, days: int = 7
    ) -> list[dict]:
        """指定日数分のコンテンツカレンダーを生成する.

        Returns:
            [{"date": "2026-03-18", "topic": ..., "category": ..., "priority": ...}, ...]
        """
        logger.info(
            "trend.generate_content_calendar.start",
            language=language,
            days=days,
        )

        # パフォーマンスデータ取得
        performance = await self.analyze_performance_patterns(language)
        best_categories = [c["category"] for c in performance.get("best_categories", [])]
        seasonal = await self.get_seasonal_themes(language)

        # ギャップカテゴリも混ぜる
        gaps = await self.analyze_content_gaps(language)
        gap_categories = [g["category"] for g in gaps if g.get("needs_more")]

        # カテゴリプールを構築 (パフォーマンス上位 + ギャップ)
        all_categories = list(dict.fromkeys(best_categories + gap_categories))
        if not all_categories:
            all_categories = ["technology", "business", "lifestyle"]

        today = date.today()
        calendar: list[dict] = []

        for i in range(days):
            target_date = today + timedelta(days=i + 1)
            # カテゴリをローテーション
            category = all_categories[i % len(all_categories)]
            # ギャップカテゴリは優先度を上げる
            priority = "high" if category in gap_categories else "medium"

            calendar.append(
                {
                    "date": target_date.isoformat(),
                    "topic": None,  # LLM で埋める
                    "category": category,
                    "priority": priority,
                    "seasonal_context": seasonal,
                }
            )

        # LLM でトピックを一括生成
        prompt = f"""Generate specific content topics for the following calendar.

Language: {language}
Seasonal themes: {json.dumps(seasonal, ensure_ascii=False)}

Calendar slots to fill:
{json.dumps([{"date": c["date"], "category": c["category"], "priority": c["priority"]} for c in calendar], ensure_ascii=False, indent=2)}

Return a JSON object with key "calendar" containing an array of objects, one per slot.
Each object must have:
- date (string): the date in YYYY-MM-DD
- topic (string): specific, engaging topic title in {language}
- category (string): the assigned category
- priority (string): "high", "medium", or "low"

Make topics specific, timely, and engaging. Avoid generic titles."""

        system_prompt = (
            "You are a content calendar planner. "
            "Return ONLY valid JSON. No markdown, no explanation."
        )

        try:
            result = await self.llm.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.5,
            )
            llm_calendar = result.get("calendar", [])

            # LLM の結果をマージ
            for entry in llm_calendar:
                for slot in calendar:
                    if slot["date"] == entry.get("date"):
                        slot["topic"] = entry.get("topic", slot["topic"])
                        break

        except Exception as exc:
            logger.warning(
                "trend.generate_calendar.llm_failed",
                error=str(exc),
            )
            # LLM 失敗時はカテゴリ名ベースのフォールバック
            for slot in calendar:
                if slot["topic"] is None:
                    slot["topic"] = f"{slot['category']} content for {slot['date']}"

        # seasonal_context はレスポンスから除去
        for slot in calendar:
            slot.pop("seasonal_context", None)

        logger.info(
            "trend.generate_content_calendar.done",
            language=language,
            entries=len(calendar),
        )
        return calendar

    # ------------------------------------------------------------------
    # 5. get_seasonal_themes
    # ------------------------------------------------------------------

    async def get_seasonal_themes(self, language: str) -> list[str]:
        """現在の月/季節に基づく関連テーマを返す.

        JP: 日本の文化イベント・ビジネスサイクルを考慮。
        EN: グローバルテック・季節トピックを考慮。
        """
        current_month = date.today().month

        # 静的マッピングからベーステーマを取得
        if language == "ja":
            base_themes = _JP_SEASONAL.get(current_month, [])
        else:
            base_themes = _EN_SEASONAL.get(current_month, [])

        # LLM で追加テーマを生成
        today = date.today()
        lang_label = "Japanese" if language == "ja" else "English"

        prompt = f"""Current date: {today.isoformat()}
Month: {today.strftime("%B")}

Suggest 3 additional timely content themes for {lang_label} audience.
Consider current tech trends, business cycles, and cultural events.

Existing themes (do not repeat): {json.dumps(base_themes, ensure_ascii=False)}

Return a JSON object with key "themes" containing an array of 3 strings."""

        system_prompt = (
            "You are a content trend analyst. "
            "Return ONLY valid JSON. No markdown."
        )

        try:
            result = await self.llm.generate_json(
                prompt=prompt,
                system_prompt=system_prompt,
                temperature=0.6,
            )
            llm_themes: list[str] = result.get("themes", [])
            all_themes = base_themes + [t for t in llm_themes if isinstance(t, str)]
        except Exception as exc:
            logger.warning(
                "trend.seasonal_themes.llm_failed",
                error=str(exc),
            )
            all_themes = base_themes

        logger.info(
            "trend.get_seasonal_themes.done",
            language=language,
            month=current_month,
            theme_count=len(all_themes),
        )
        return all_themes

    # ------------------------------------------------------------------
    # 6. evaluate_topic_saturation
    # ------------------------------------------------------------------

    async def evaluate_topic_saturation(
        self, category: str, language: str
    ) -> dict:
        """カテゴリの飽和度を評価する.

        Returns:
            {"saturated": bool, "count": int, "avg_score": float, "recommendation": str}
        """
        logger.info(
            "trend.evaluate_topic_saturation.start",
            category=category,
            language=language,
        )

        # 件数と平均スコア
        rows = await self.db.fetch_all(
            """
            SELECT COUNT(*)                      AS count,
                   ROUND(AVG(quality_score), 1)   AS avg_score
              FROM contents
             WHERE language = ? AND category = ? AND status = 'published'
            """,
            (language, category),
        )

        count = rows[0]["count"] if rows else 0
        avg_score = rows[0]["avg_score"] if rows and rows[0]["avg_score"] else 0.0

        # スコアトレンド (直近 vs 全体)
        recent_rows = await self.db.fetch_all(
            """
            SELECT ROUND(AVG(ql.score), 1) AS recent_avg
              FROM quality_logs ql
              JOIN contents c ON c.id = ql.content_id
             WHERE c.language = ? AND c.category = ?
               AND ql.created_at >= DATE('now', '-14 days')
            """,
            (language, category),
        )
        recent_avg = (
            recent_rows[0]["recent_avg"]
            if recent_rows and recent_rows[0]["recent_avg"]
            else 0.0
        )

        # 全カテゴリの平均件数を取得して比較
        all_cats = await self.db.fetch_all(
            """
            SELECT COUNT(*) AS cnt
              FROM contents
             WHERE language = ? AND status = 'published' AND category IS NOT NULL
             GROUP BY category
            """,
            (language,),
        )
        avg_count = (
            sum(r["cnt"] for r in all_cats) / len(all_cats) if all_cats else 0
        )

        # 飽和判定ロジック
        saturated = False
        if count > avg_count * 2 and recent_avg < avg_score:
            saturated = True
        elif count > avg_count * 3:
            saturated = True

        # レコメンデーション生成
        if saturated:
            recommendation = (
                f"Category '{category}' is saturated with {count} contents. "
                "Consider focusing on other categories or finding a unique angle."
            )
        elif count < avg_count * 0.5:
            recommendation = (
                f"Category '{category}' is underrepresented ({count} contents). "
                "High opportunity for new content."
            )
        elif recent_avg >= 80:
            recommendation = (
                f"Category '{category}' performs well (recent avg: {recent_avg}). "
                "Continue creating content but diversify angles."
            )
        else:
            recommendation = (
                f"Category '{category}' has moderate coverage ({count} contents, "
                f"avg score: {avg_score}). Room for quality improvement."
            )

        result = {
            "saturated": saturated,
            "count": count,
            "avg_score": avg_score,
            "recent_avg_score": recent_avg,
            "recommendation": recommendation,
        }

        logger.info(
            "trend.evaluate_topic_saturation.done",
            category=category,
            language=language,
            saturated=saturated,
            count=count,
        )
        return result

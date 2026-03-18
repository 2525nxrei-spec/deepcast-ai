"""Deepcast Engine — コンテンツ自己評価・品質スコアリングエンジン."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from config.settings import settings

if TYPE_CHECKING:
    from core.database import DatabaseManager
    from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class EvaluationResult(BaseModel):
    """LLM による品質評価の結果."""

    overall_score: int = Field(ge=0, le=100)
    naturalness: int = Field(default=50, ge=0, le=100)
    engagement: int = Field(default=50, ge=0, le=100)
    seo_quality: int = Field(default=50, ge=0, le=100)
    structure: int = Field(default=50, ge=0, le=100)
    originality: int = Field(default=50, ge=0, le=100)
    feedback: str = ""
    suggestions: list[str] = []


# ---------------------------------------------------------------------------
# Conservative fallback when all retries fail
# ---------------------------------------------------------------------------

_FALLBACK_RESULT = EvaluationResult(
    overall_score=50,
    naturalness=50,
    engagement=50,
    seo_quality=50,
    structure=50,
    originality=50,
    feedback="Evaluation failed after all retries. Conservative fallback score applied.",
    suggestions=["Re-run evaluation when the model is available."],
)

# ---------------------------------------------------------------------------
# Evaluation prompt templates
# ---------------------------------------------------------------------------

_EVALUATION_SYSTEM_PROMPT = (
    "You are a strict content quality evaluator. "
    "Evaluate the following content and return ONLY valid JSON with no markdown formatting, "
    "no code fences, no extra text. The JSON must have these exact keys: "
    "overall_score, naturalness, engagement, seo_quality, structure, originality, "
    "feedback, suggestions. All scores are integers 0-100. "
    "suggestions is a list of strings. feedback is a string."
)

_EVALUATION_USER_PROMPT_TEMPLATE = (
    "Evaluate this {language} content.\n\n"
    "Title: {title}\n\n"
    "Body:\n{body}\n\n"
    "Return ONLY the JSON evaluation."
)

_PROMPT_IMPROVEMENT_SYSTEM = (
    "You are an expert prompt engineer. "
    "Analyze the feedback from recent low-scoring content evaluations "
    "and suggest an improved system prompt for the content generation model."
)

_PROMPT_IMPROVEMENT_USER_TEMPLATE = (
    "Language: {language}\n\n"
    "Recent low-scoring evaluations:\n{evaluations}\n\n"
    "Based on these recurring issues, write an improved system prompt "
    "that would help the generation model avoid these problems. "
    "Return the improved system prompt as plain text."
)


# ---------------------------------------------------------------------------
# ContentEvaluator
# ---------------------------------------------------------------------------


class ContentEvaluator:
    """コンテンツの品質を LLM で自動評価し、スコアを記録する."""

    def __init__(self, llm: LLMClient, db: DatabaseManager) -> None:
        self._llm = llm
        self._db = db
        self._model = settings.OLLAMA_MODEL_EVALUATE
        self._max_retries = settings.MAX_RETRIES

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def evaluate(
        self,
        content_title: str,
        content_body: str,
        language: str,
    ) -> EvaluationResult:
        """コンテンツを評価し *EvaluationResult* を返す.

        最大 ``MAX_RETRIES`` 回リトライし、すべて失敗した場合は
        保守的なスコア 50 のフォールバック結果を返す。
        """
        user_prompt = _EVALUATION_USER_PROMPT_TEMPLATE.format(
            language=language,
            title=content_title,
            body=content_body,
        )

        last_error: Exception | None = None

        for attempt in range(1, self._max_retries + 1):
            try:
                raw = await self._llm.generate(
                    prompt=user_prompt,
                    system_prompt=_EVALUATION_SYSTEM_PROMPT,
                    model=self._model,
                )
                result = self._parse_evaluation(raw)
                logger.info(
                    "evaluation_success",
                    attempt=attempt,
                    overall_score=result.overall_score,
                    language=language,
                )
                return result
            except (json.JSONDecodeError, ValueError, KeyError) as exc:
                last_error = exc
                logger.warning(
                    "evaluation_parse_failed",
                    attempt=attempt,
                    error=str(exc),
                )
            except Exception as exc:  # noqa: BLE001
                last_error = exc
                logger.error(
                    "evaluation_llm_error",
                    attempt=attempt,
                    error=str(exc),
                )

        logger.error(
            "evaluation_all_retries_failed",
            last_error=str(last_error),
            language=language,
        )
        return _FALLBACK_RESULT.model_copy()

    async def evaluate_and_log(
        self,
        content_id: int,
        content_title: str,
        content_body: str,
        language: str,
    ) -> EvaluationResult:
        """評価を実行し、結果を DB の quality_logs に保存する."""
        result = await self.evaluate(content_title, content_body, language)

        await self._db.save_quality_log(
            content_id=content_id,
            score=result.overall_score,
            feedback=result.feedback,
            evaluator_model=self._model,
        )

        logger.info(
            "evaluation_logged",
            content_id=content_id,
            overall_score=result.overall_score,
        )
        return result

    async def get_quality_trend(
        self,
        language: str,
        days: int = 7,
    ) -> dict:
        """指定期間の品質トレンドを返す.

        Returns:
            {"avg_score": float, "trend": str, "total_evaluated": int}
        """
        trend_data = await self._db.get_quality_trend(language, days)

        if not trend_data:
            return {"avg_score": 0.0, "trend": "stable", "total_evaluated": 0}

        scores = [row["avg_score"] for row in trend_data]
        total = sum(row["count"] for row in trend_data)
        avg = sum(row["avg_score"] * row["count"] for row in trend_data) / total if total else 0.0

        trend = self._compute_trend(scores)

        return {
            "avg_score": round(avg, 2),
            "trend": trend,
            "total_evaluated": total,
        }

    async def should_adjust_prompts(self, language: str) -> bool:
        """直近 7 日間で品質が 10 ポイント以上低下していれば True."""
        trend_data = await self._db.get_quality_trend(language, days=7)

        if len(trend_data) < 2:
            return False

        scores = [row["avg_score"] for row in trend_data]
        mid = len(scores) // 2
        first_half_avg = sum(scores[:mid]) / mid
        second_half_avg = sum(scores[mid:]) / (len(scores) - mid)

        drop = first_half_avg - second_half_avg
        should = drop > 10

        logger.info(
            "prompt_adjustment_check",
            language=language,
            first_half_avg=round(first_half_avg, 2),
            second_half_avg=round(second_half_avg, 2),
            drop=round(drop, 2),
            should_adjust=should,
        )
        return should

    async def suggest_prompt_improvements(self, language: str) -> str:
        """低スコアコンテンツのフィードバックを分析し、プロンプト改善案を返す."""
        # quality_logs テーブルから低スコアのフィードバックを取得
        db = await self._db._get_connection()
        cursor = await db.execute(
            """
            SELECT score, feedback
            FROM quality_logs
            WHERE score < ?
            ORDER BY score ASC
            LIMIT 10
            """,
            (settings.QUALITY_THRESHOLD,),
        )
        rows = await cursor.fetchall()

        if not rows:
            return "No low-scoring content found. Current prompts appear effective."

        evaluations_text = "\n\n".join(
            f"Score: {row['score']}\n"
            f"Feedback: {row['feedback']}"
            for row in rows
        )

        user_prompt = _PROMPT_IMPROVEMENT_USER_TEMPLATE.format(
            language=language,
            evaluations=evaluations_text,
        )

        suggestion = await self._llm.generate(
            prompt=user_prompt,
            system_prompt=_PROMPT_IMPROVEMENT_SYSTEM,
            model=self._model,
        )

        logger.info(
            "prompt_improvement_suggested",
            language=language,
            low_score_count=len(rows),
        )
        return suggestion

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _parse_evaluation(raw: str) -> EvaluationResult:
        """LLM の生テキスト出力を *EvaluationResult* にパースする."""
        # LLM がコードフェンスで囲んでくる場合に対応
        cleaned = raw.strip()
        if cleaned.startswith("```"):
            # Remove opening fence (e.g. ```json)
            first_newline = cleaned.index("\n")
            cleaned = cleaned[first_newline + 1 :]
        if cleaned.endswith("```"):
            cleaned = cleaned[: -len("```")]
        cleaned = cleaned.strip()

        data = json.loads(cleaned)
        return EvaluationResult(**data)

    @staticmethod
    def _compute_trend(scores: list[int]) -> str:
        """スコアリストから傾向を判定する."""
        if len(scores) < 2:
            return "stable"

        mid = len(scores) // 2
        first_avg = sum(scores[:mid]) / mid
        second_avg = sum(scores[mid:]) / (len(scores) - mid)
        diff = second_avg - first_avg

        if diff > 5:
            return "improving"
        if diff < -5:
            return "declining"
        return "stable"

"""Deepcast Engine — コンテンツ自動生成エンジン."""

from __future__ import annotations

import json
import re
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, ValidationError, field_validator

from config.settings import settings

if TYPE_CHECKING:
    from core.database import DatabaseManager
    from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class TopicIdea(BaseModel):
    """トピックアイデアの構造."""

    title: str
    category: str
    keywords: list[str]
    target_audience: str
    angle: str  # unique perspective

    @field_validator("target_audience", mode="before")
    @classmethod
    def _coerce_target_audience(cls, v: object) -> str:
        """LLM がリストで返す場合があるため、文字列に変換する."""
        if isinstance(v, list):
            return ", ".join(str(item) for item in v)
        return str(v)


class GeneratedContent(BaseModel):
    """生成コンテンツの構造."""

    title: str
    body: str
    summary: str
    tags: list[str]
    category: str
    seo_keywords: list[str]
    estimated_read_time: int  # minutes


# ---------------------------------------------------------------------------
# Language-specific generation parameters
# ---------------------------------------------------------------------------

_LANG_PARAMS: dict[str, dict] = {
    "ja": {
        "temperature": 0.8,
        "min_length_hint": "3000文字以上",
        "style_hint": "魅力的で会話調、ポッドキャスト・ディスカッション風",
    },
    "en": {
        "temperature": 0.6,
        "min_length_hint": "1500+ words",
        "style_hint": "structured, authoritative, well-organized with headings",
    },
}


# ---------------------------------------------------------------------------
# ContentGenerator
# ---------------------------------------------------------------------------


class ContentGenerator:
    """LLM を使ったコンテンツ生成エンジン.

    Parameters
    ----------
    llm_client:
        Ollama / OpenAI 互換の LLM クライアント.
    db:
        SQLite ベースのデータベースマネージャー.
    prompts_path:
        ``config/prompts.json`` へのパス (省略時はデフォルト).
    """

    def __init__(
        self,
        llm_client: LLMClient,
        db: DatabaseManager,
        prompts_path: str | Path | None = None,
    ) -> None:
        self.llm = llm_client
        self.db = db
        self.max_retries: int = settings.MAX_RETRIES

        # Load prompt templates ------------------------------------------
        if prompts_path is None:
            prompts_path = Path(__file__).resolve().parents[1] / "config" / "prompts.json"
        else:
            prompts_path = Path(prompts_path)

        with prompts_path.open("r", encoding="utf-8") as f:
            self.prompts: dict = json.load(f)

        logger.info(
            "content_generator.initialized",
            prompts_loaded=list(self.prompts.keys()),
            max_retries=self.max_retries,
        )

    # ------------------------------------------------------------------
    # 1. research_topics
    # ------------------------------------------------------------------

    async def research_topics(
        self,
        language: str,
        count: int = 5,
    ) -> list[TopicIdea]:
        """LLM でトピックアイデアを生成し、DB 重複チェック後に保存して返す.

        Parameters
        ----------
        language:
            ``"ja"`` or ``"en"``.
        count:
            生成するアイデア数.

        Returns
        -------
        list[TopicIdea]
            重複を除いた新規トピックのリスト.
        """
        log = logger.bind(language=language, requested_count=count)
        log.info("research_topics.start")

        # Build prompt ---------------------------------------------------
        prompt_key = f"topic_research_{language}"
        prompt_data = self.prompts.get(prompt_key, {})
        system_prompt = prompt_data.get("content", "") if isinstance(prompt_data, dict) else str(prompt_data)
        if not system_prompt:
            system_prompt = "You are a topic researcher. Generate unique topic ideas as a JSON array."
        user_prompt = (
            f"Generate exactly {count} unique topic ideas. "
            f"Language: {'Japanese' if language == 'ja' else 'English'}. "
            "Respond ONLY with a JSON array of objects, each having keys: "
            '"title", "category" (one of: technology, society, economy, psychology, philosophy, science), '
            '"keywords" (list of 3-5 strings), "target_audience", "angle". '
            "Do NOT include any text outside the JSON array."
        )

        # Call LLM (use generate_json for structured output) ---------------
        try:
            data = await self.llm.generate_json(
                prompt=user_prompt,
                system_prompt=system_prompt,
            )
            # generate_json returns dict; wrap topics list if needed
            if isinstance(data, dict):
                for key in ("topics", "topic_ideas", "ideas", "results"):
                    if key in data and isinstance(data[key], list):
                        data = data[key]
                        break
                else:
                    data = [data]
            topics = [TopicIdea.model_validate(item) for item in (data if isinstance(data, list) else [data])[:count]]
        except Exception:
            # Fallback: use generate() and parse
            params = _LANG_PARAMS.get(language, _LANG_PARAMS["en"])
            raw = await self.llm.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=params["temperature"],
            )
            topics = self._parse_topic_list(raw, count)
        log.info("research_topics.parsed", parsed_count=len(topics))

        # De-duplicate against DB ----------------------------------------
        new_topics: list[TopicIdea] = []
        for topic in topics:
            if await self.db.check_duplicate(topic.title, language):
                log.debug("research_topics.duplicate_skipped", title=topic.title)
                continue
            await self.db.save_topic(
                title=topic.title,
                language=language,
                category=topic.category,
                keywords=topic.keywords,
            )
            new_topics.append(topic)

        log.info("research_topics.done", new_count=len(new_topics))
        return new_topics

    # ------------------------------------------------------------------
    # 2. generate_content
    # ------------------------------------------------------------------

    async def generate_content(
        self,
        topic: TopicIdea,
        language: str,
    ) -> GeneratedContent:
        """トピックからコンテンツを生成する.

        バリデーション失敗時は最大 ``MAX_RETRIES`` 回リトライする。

        Parameters
        ----------
        topic:
            生成対象のトピック.
        language:
            ``"ja"`` or ``"en"``.

        Returns
        -------
        GeneratedContent
            バリデーション済みの生成コンテンツ.

        Raises
        ------
        ValueError
            全リトライ失敗時.
        """
        log = logger.bind(topic_title=topic.title, language=language)
        log.info("generate_content.start")

        params = _LANG_PARAMS.get(language, _LANG_PARAMS["en"])

        prompt_key = f"{language}_generate"
        prompt_data = self.prompts.get(prompt_key, {})
        system_prompt = prompt_data.get("content", "") if isinstance(prompt_data, dict) else str(prompt_data)
        if not system_prompt:
            system_prompt = (
                "あなたは日本語コンテンツライターです。高品質なコンテンツを生成してください。"
                if language == "ja"
                else "You are a content writer. Generate high-quality content."
            )

        user_prompt = self._build_content_prompt(topic, language, params)

        last_error: Exception | None = None
        for attempt in range(1, self.max_retries + 1):
            log.info("generate_content.attempt", attempt=attempt)

            try:
                # Try generate_json first for structured output
                data = await self.llm.generate_json(
                    prompt=user_prompt,
                    system_prompt=system_prompt + "\n\nIMPORTANT: Respond ONLY with valid JSON.",
                )
                content = GeneratedContent.model_validate(data)
                log.info("generate_content.success", attempt=attempt)
                return content
            except Exception:
                pass

            # Fallback: generate raw text and parse
            try:
                raw = await self.llm.generate(
                    prompt=user_prompt,
                    system_prompt=system_prompt,
                    temperature=params["temperature"],
                )
                content = self._parse_generated_content(raw)
                log.info("generate_content.success", attempt=attempt)
                return content
            except (ValidationError, ValueError, json.JSONDecodeError) as exc:
                last_error = exc
                log.warning(
                    "generate_content.validation_failed",
                    attempt=attempt,
                    error=str(exc),
                )

        msg = (
            f"Content generation failed after {self.max_retries} attempts "
            f"for topic '{topic.title}': {last_error}"
        )
        log.error("generate_content.all_retries_failed", error=msg)
        raise ValueError(msg)

    # ------------------------------------------------------------------
    # 3. generate_with_quality_gate
    # ------------------------------------------------------------------

    async def generate_with_quality_gate(
        self,
        topic: TopicIdea,
        language: str,
        min_score: int = 80,
    ) -> GeneratedContent | None:
        """品質ゲート付きコンテンツ生成.

        生成 → 品質評価 → スコアが ``min_score`` 未満なら再生成。
        全試行を DB に記録する。

        Parameters
        ----------
        topic:
            生成対象のトピック.
        language:
            ``"ja"`` or ``"en"``.
        min_score:
            合格とみなす最低スコア (0-100).

        Returns
        -------
        GeneratedContent | None
            品質基準を満たしたコンテンツ。全試行失敗時は ``None``.
        """
        log = logger.bind(
            topic_title=topic.title,
            language=language,
            min_score=min_score,
        )
        log.info("quality_gate.start")

        for attempt in range(1, self.max_retries + 1):
            log.info("quality_gate.attempt", attempt=attempt)

            try:
                content = await self.generate_content(topic, language)
            except ValueError:
                log.warning("quality_gate.generation_failed", attempt=attempt)
                continue

            # Evaluate quality using the evaluator -----------------------
            score = await self._evaluate_quality(content, language)
            passed = score >= min_score

            if passed:
                log.info(
                    "quality_gate.passed",
                    attempt=attempt,
                    score=score,
                )
                content_id = await self.db.save_content(
                    title=content.title,
                    body=content.body,
                    language=language,
                    category=content.category,
                    tags=content.tags,
                    quality_score=score,
                    status="published",
                    topic_source=topic.title,
                )
                await self.db.save_quality_log(
                    content_id=content_id,
                    score=score,
                    feedback="ok",
                )
                return content

            log.warning(
                "quality_gate.below_threshold",
                attempt=attempt,
                score=score,
                min_score=min_score,
            )
            # Save rejected content for audit
            content_id = await self.db.save_content(
                title=content.title,
                body=content.body,
                language=language,
                category=content.category,
                tags=content.tags,
                quality_score=score,
                status="rejected",
                topic_source=topic.title,
            )
            await self.db.save_quality_log(
                content_id=content_id,
                score=score,
                feedback=f"score_{score}_below_{min_score}",
            )

        log.error("quality_gate.all_attempts_failed")
        return None

    # ==================================================================
    # Private helpers
    # ==================================================================

    def _build_content_prompt(
        self,
        topic: TopicIdea,
        language: str,
        params: dict,
    ) -> str:
        """トピック情報からコンテンツ生成用のユーザープロンプトを組み立てる."""
        if language == "ja":
            return (
                f"以下のトピックに基づいて、日本語で記事を書いてください。\n"
                f"【重要】出力は必ず日本語のみ。英語で書くのは禁止です。\n\n"
                f"タイトル: {topic.title}\n"
                f"カテゴリ: {topic.category}\n"
                f"キーワード: {', '.join(topic.keywords)}\n"
                f"ターゲット読者: {topic.target_audience}\n"
                f"記事の切り口: {topic.angle}\n\n"
                f"条件:\n"
                f"- 言語: 日本語\n"
                f"- 最低文字数: {params['min_length_hint']}\n"
                f"- スタイル: {params['style_hint']}\n\n"
                "以下のキーを持つJSONオブジェクトのみを返してください: "
                '"title", "body", "summary", "tags" (配列), "category", '
                '"seo_keywords" (配列), "estimated_read_time" (整数、分)。'
            )
        return (
            f"Write a full article based on the following topic.\n\n"
            f"Title: {topic.title}\n"
            f"Category: {topic.category}\n"
            f"Keywords: {', '.join(topic.keywords)}\n"
            f"Target audience: {topic.target_audience}\n"
            f"Unique angle: {topic.angle}\n\n"
            f"Requirements:\n"
            f"- Language: {language}\n"
            f"- Minimum length: {params['min_length_hint']}\n"
            f"- Style: {params['style_hint']}\n\n"
            "Respond ONLY with a JSON object having keys: "
            '"title", "body", "summary", "tags" (list), "category", '
            '"seo_keywords" (list), "estimated_read_time" (int, minutes).'
        )

    @staticmethod
    def _extract_json(raw: str) -> str:
        """LLM の生テキストから JSON 部分を抽出する."""
        text = raw.strip()
        # Strip markdown fences
        if "```" in text:
            m = re.search(r"```(?:json)?\s*\n?(.*?)```", text, re.DOTALL)
            if m:
                text = m.group(1).strip()
        # Try to find JSON array or object
        for start_char, end_char in [("[", "]"), ("{", "}")]:
            start = text.find(start_char)
            if start == -1:
                continue
            depth = 0
            for i in range(start, len(text)):
                if text[i] == start_char:
                    depth += 1
                elif text[i] == end_char:
                    depth -= 1
                if depth == 0:
                    return text[start : i + 1]
        return text

    @staticmethod
    def _try_fix_json(text: str) -> str:
        """不正なJSONの一般的な問題を修復する."""
        # Remove trailing commas before } or ]
        text = re.sub(r',\s*([}\]])', r'\1', text)
        # Fix single quotes to double quotes
        text = text.replace("'", '"')
        # Remove control characters
        text = re.sub(r'[\x00-\x1f\x7f]', ' ', text)
        return text

    @staticmethod
    def _parse_topic_list(raw: str, expected: int) -> list[TopicIdea]:
        """LLM の生テキストから TopicIdea リストをパースする."""
        text = ContentGenerator._extract_json(raw)
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            text = ContentGenerator._try_fix_json(text)
            data = json.loads(text)
        if isinstance(data, dict):
            # LLM might wrap in {"topics": [...]}
            for key in ("topics", "topic_ideas", "ideas", "results"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                data = [data]
        if not isinstance(data, list):
            raise ValueError("Expected a JSON array of topics")

        return [TopicIdea.model_validate(item) for item in data[:expected]]

    @staticmethod
    def _parse_generated_content(raw: str) -> GeneratedContent:
        """LLM の生テキストから GeneratedContent をパースする."""
        text = ContentGenerator._extract_json(raw)
        data = json.loads(text)
        return GeneratedContent.model_validate(data)

    async def _evaluate_quality(
        self,
        content: GeneratedContent,
        language: str,
    ) -> int:
        """LLM を使ってコンテンツの品質を 0-100 で評価する."""
        prompt_key = f"{language}_evaluate"
        prompt_data = self.prompts.get(prompt_key, {})
        system_prompt = prompt_data.get("content", "") if isinstance(prompt_data, dict) else str(prompt_data)
        if not system_prompt:
            system_prompt = "Evaluate the content quality. Return only an integer score 0-100."

        user_prompt = (
            "Evaluate the following article on a scale of 0-100. "
            "Consider: accuracy, readability, depth, engagement, SEO optimization.\n\n"
            f"Title: {content.title}\n"
            f"Summary: {content.summary}\n"
            f"Body (first 500 chars): {content.body[:500]}\n"
            f"Tags: {', '.join(content.tags)}\n"
            f"SEO Keywords: {', '.join(content.seo_keywords)}\n\n"
            "Respond with ONLY a single integer (0-100)."
        )

        raw = await self.llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
            temperature=0.1,
        )

        try:
            score = int(raw.strip())
        except ValueError:
            # Try to extract a number from the response
            match = re.search(r"\b(\d{1,3})\b", raw)
            score = int(match.group(1)) if match else 50
            logger.warning(
                "quality_evaluation.parse_fallback",
                raw_response=raw[:100],
                extracted_score=score,
            )

        return max(0, min(100, score))

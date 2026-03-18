"""Deepcast Engine -- Central Brain: Planner -> Creator -> Editor -> Publisher.

マルチエージェントパイプラインを統括するオーケストレーター。
各ステップを AgentTask として管理し、計画 -> 生成 -> 編集 -> 公開 の
一連のフローを実行する。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from typing import Any

import structlog
from pydantic import BaseModel, Field

from config.settings import settings
from core.database import DatabaseManager
from core.llm_client import LLMClient
from engine.evaluator import ContentEvaluator, EvaluationResult
from engine.generator import ContentGenerator, GeneratedContent, TopicIdea

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & Pydantic models
# ---------------------------------------------------------------------------


class AgentRole(str, Enum):
    """パイプライン内のエージェント役割."""

    PLANNER = "planner"
    CREATOR = "creator"
    EDITOR = "editor"
    PUBLISHER = "publisher"


class AgentTask(BaseModel):
    """パイプラインの各ステップを表すタスク."""

    role: AgentRole
    status: str = "pending"  # pending, running, completed, failed
    input_data: dict = Field(default_factory=dict)
    output_data: dict | None = None
    started_at: datetime | None = None
    completed_at: datetime | None = None
    error: str | None = None


class SNSSummary(BaseModel):
    """SNS 投稿用サマリー."""

    x_post: str = Field(max_length=140)  # X (Twitter) 用: 最大 140 文字
    note_summary: str = Field(max_length=500)  # note 用: 最大 500 文字
    og_description: str = Field(max_length=160)  # OGP 用: 最大 160 文字


class FAQItem(BaseModel):
    """FAQ の 1 項目."""

    question: str
    answer: str


class ContentMetadata(BaseModel):
    """コンテンツに付与するメタデータ (SNS / FAQ / SEO)."""

    sns: SNSSummary
    faq: list[FAQItem]
    seo_title: str
    seo_description: str
    seo_keywords: list[str]


# ---------------------------------------------------------------------------
# Brain
# ---------------------------------------------------------------------------


class Brain:
    """Central orchestrator implementing Planner -> Creator -> Editor -> Publisher pipeline."""

    def __init__(
        self,
        llm: LLMClient,
        db: DatabaseManager,
        generator: ContentGenerator,
        evaluator: ContentEvaluator,
    ) -> None:
        self._llm = llm
        self._db = db
        self._generator = generator
        self._evaluator = evaluator
        self._last_run: datetime | None = None
        self._success_count: int = 0
        self._fail_count: int = 0

    # ------------------------------------------------------------------
    # 1. plan
    # ------------------------------------------------------------------

    async def plan(self, language: str) -> list[AgentTask]:
        """PLANNER エージェント: 過去の実績を分析し、生成計画を立てる.

        Parameters
        ----------
        language:
            ``"ja"`` or ``"en"``.

        Returns
        -------
        list[AgentTask]
            Creator に渡すタスクのリスト。
        """
        log = logger.bind(agent="planner", language=language)
        log.info("plan.start")

        # --- 過去データ収集 ------------------------------------------------
        # カテゴリ別スコア
        category_stats = await self._db.fetch_all(
            """
            SELECT c.category,
                   COUNT(*) AS cnt,
                   CAST(AVG(ql.score) AS INTEGER) AS avg_score
            FROM quality_logs ql
            JOIN contents c ON c.id = ql.content_id
            WHERE c.language = ?
            GROUP BY c.category
            ORDER BY avg_score DESC
            """,
            (language,),
        )

        # 直近公開済みカテゴリ (多様性チェック用)
        recent_categories = await self._db.fetch_all(
            """
            SELECT category FROM contents
            WHERE language = ? AND status = 'published'
            ORDER BY created_at DESC LIMIT 10
            """,
            (language,),
        )
        recent_cat_list = [r["category"] for r in recent_categories if r.get("category")]

        # pending トピック
        pending_topics = await self._db.get_pending_topics(language, limit=10)

        # --- LLM に計画を立てさせる ----------------------------------------
        analysis_summary = json.dumps(
            {
                "category_stats": category_stats,
                "recent_categories": recent_cat_list,
                "pending_topic_count": len(pending_topics),
                "quality_threshold": settings.QUALITY_THRESHOLD,
            },
            ensure_ascii=False,
        )

        system_prompt = (
            "You are a strategic content planner. Analyze the performance data and "
            "decide which topics to create next. Prioritize underserved categories, "
            "avoid repeating recent categories, and aim for high-quality scores. "
            "Return a JSON array of objects with keys: "
            '"title", "category", "keywords" (list), "target_audience", "angle", "format". '
            f"Language: {language}. Generate 1-3 topic plans."
        )

        user_prompt = (
            f"Performance data:\n{analysis_summary}\n\n"
            f"Pending topics in queue: {json.dumps([t.get('title', '') for t in pending_topics], ensure_ascii=False)}\n\n"
            "Based on this data, plan the next content pieces. "
            "Focus on gaps and opportunities."
        )

        try:
            raw = await self._llm.generate(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.7,
            )
            plans = self._parse_plan_response(raw)
        except Exception as exc:
            log.error("plan.llm_failed", error=str(exc))
            # フォールバック: pending トピックがあればそれを使う
            plans = []
            for topic in pending_topics[:3]:
                plans.append(
                    {
                        "title": topic.get("title", "Untitled"),
                        "category": topic.get("category", "general"),
                        "keywords": topic.get("keywords", []),
                        "target_audience": "general audience",
                        "angle": "informative overview",
                        "format": "article",
                    }
                )

        if not plans:
            # pending トピックもない場合は research_topics で新規生成
            log.info("plan.no_plans_from_llm, researching new topics")
            new_topics = await self._generator.research_topics(language, count=3)
            for topic in new_topics:
                plans.append(
                    {
                        "title": topic.title,
                        "category": topic.category,
                        "keywords": topic.keywords,
                        "target_audience": topic.target_audience,
                        "angle": topic.angle,
                        "format": "article",
                    }
                )

        # AgentTask に変換
        tasks: list[AgentTask] = []
        for plan_item in plans:
            task = AgentTask(
                role=AgentRole.CREATOR,
                status="pending",
                input_data={
                    "language": language,
                    "topic": plan_item,
                },
            )
            tasks.append(task)

        log.info("plan.done", planned_count=len(tasks))
        await self._log("info", f"Planned {len(tasks)} content pieces", language)
        return tasks

    # ------------------------------------------------------------------
    # 2. create
    # ------------------------------------------------------------------

    async def create(self, task: AgentTask) -> AgentTask:
        """CREATOR エージェント: 計画に基づきコンテンツを生成する.

        Parameters
        ----------
        task:
            input_data に ``topic`` と ``language`` を含む AgentTask。

        Returns
        -------
        AgentTask
            output_data に生成コンテンツを格納して返す。
        """
        log = logger.bind(agent="creator")
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)

        topic_data = task.input_data.get("topic", {})
        language = task.input_data.get("language", "ja")

        log.info("create.start", title=topic_data.get("title"))

        try:
            topic_idea = TopicIdea(
                title=topic_data.get("title", ""),
                category=topic_data.get("category", "general"),
                keywords=topic_data.get("keywords", []),
                target_audience=topic_data.get("target_audience", "general audience"),
                angle=topic_data.get("angle", "informative overview"),
            )

            content: GeneratedContent = await self._generator.generate_content(
                topic_idea, language
            )

            task.output_data = {
                "content": content.model_dump(),
                "language": language,
                "topic": topic_data,
            }
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            log.info("create.done", title=content.title)

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            log.error("create.failed", error=str(exc))

        return task

    # ------------------------------------------------------------------
    # 3. edit
    # ------------------------------------------------------------------

    async def edit(self, task: AgentTask) -> AgentTask:
        """EDITOR エージェント: 品質評価・改善・メタデータ生成を行う.

        処理内容:
        a. ContentEvaluator で品質スコアを算出
        b. スコアが閾値未満の場合、弱点を特定して LLM でリライト
        c. SEO メタデータ生成 (タイトル最適化、meta description、keywords)
        d. SNS サマリー生成 (X 140字、note 500字、FAQ 3-5 件)

        Parameters
        ----------
        task:
            output_data に ``content`` を含む AgentTask (Creator から受け取る)。

        Returns
        -------
        AgentTask
            output_data に編集済みコンテンツ + メタデータを格納して返す。
        """
        log = logger.bind(agent="editor")
        task.role = AgentRole.EDITOR
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)

        try:
            if task.output_data is None:
                raise ValueError("output_data is None")
            content_data: dict = task.output_data.get("content", {})
            language: str = task.output_data.get("language", "ja")
            title = content_data.get("title", "")
            body = content_data.get("body", "")

            log.info("edit.start", title=title)

            # --- a. 品質評価 -----------------------------------------------
            evaluation: EvaluationResult = await self._evaluator.evaluate(
                content_title=title,
                content_body=body,
                language=language,
            )

            log.info(
                "edit.evaluation_done",
                overall_score=evaluation.overall_score,
                threshold=settings.QUALITY_THRESHOLD,
            )

            # --- b. スコアが閾値未満ならリライト ----------------------------
            if evaluation.overall_score < settings.QUALITY_THRESHOLD:
                log.info("edit.rewriting", reason="below_threshold")
                body, title = await self._rewrite_weak_areas(
                    title=title,
                    body=body,
                    language=language,
                    evaluation=evaluation,
                )
                content_data["title"] = title
                content_data["body"] = body

                # リライト後に再評価
                evaluation = await self._evaluator.evaluate(
                    content_title=title,
                    content_body=body,
                    language=language,
                )
                log.info(
                    "edit.re_evaluation_done",
                    overall_score=evaluation.overall_score,
                )

            # --- c & d. メタデータ生成 (SEO + SNS + FAQ) -------------------
            metadata: ContentMetadata = await self._generate_metadata(
                title=title,
                body=body,
                language=language,
            )

            # 結果をまとめる
            task.output_data = {
                "content": content_data,
                "language": language,
                "topic": task.output_data.get("topic", {}),
                "evaluation": evaluation.model_dump(),
                "metadata": metadata.model_dump(),
            }
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)
            log.info("edit.done", title=title, score=evaluation.overall_score)

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            log.error("edit.failed", error=str(exc))

        return task

    # ------------------------------------------------------------------
    # 4. publish
    # ------------------------------------------------------------------

    async def publish(self, task: AgentTask) -> AgentTask:
        """PUBLISHER エージェント: 最終コンテンツを DB に保存・公開する.

        Parameters
        ----------
        task:
            output_data に ``content``, ``evaluation``, ``metadata`` を含む AgentTask。

        Returns
        -------
        AgentTask
            公開完了後のタスク。output_data に content_id を追加。
        """
        log = logger.bind(agent="publisher")
        task.role = AgentRole.PUBLISHER
        task.status = "running"
        task.started_at = datetime.now(timezone.utc)

        try:
            if task.output_data is None:
                raise ValueError("output_data is None")
            content_data: dict = task.output_data.get("content", {})
            language: str = task.output_data.get("language", "ja")
            evaluation: dict = task.output_data.get("evaluation", {})
            metadata: dict = task.output_data.get("metadata", {})
            topic_data: dict = task.output_data.get("topic", {})

            score = evaluation.get("overall_score", 0)
            title = content_data.get("title", "Untitled")

            log.info("publish.start", title=title, score=score)

            # 品質閾値を満たしているか最終判定
            status = "published" if score >= settings.QUALITY_THRESHOLD else "draft"

            # DB にコンテンツ保存
            content_id = await self._db.save_content(
                title=title,
                body=content_data.get("body", ""),
                language=language,
                category=content_data.get("category"),
                tags=content_data.get("tags"),
                quality_score=score,
                status=status,
                topic_source=topic_data.get("title"),
                metadata=metadata,
            )

            # 品質ログ保存
            await self._db.save_quality_log(
                content_id=content_id,
                score=score,
                feedback=evaluation.get("feedback", ""),
                evaluator_model=settings.OLLAMA_MODEL_EVALUATE,
            )

            # 公開イベントをシステムログに記録
            await self._db.save_system_log(
                level="INFO",
                message=(
                    f"Content published: id={content_id}, title='{title}', "
                    f"score={score}, status={status}"
                ),
                component="brain.publisher",
            )

            task.output_data["content_id"] = content_id
            task.output_data["final_status"] = status
            task.status = "completed"
            task.completed_at = datetime.now(timezone.utc)

            self._success_count += 1
            log.info(
                "publish.done",
                content_id=content_id,
                status=status,
                score=score,
            )

        except Exception as exc:
            task.status = "failed"
            task.error = str(exc)
            task.completed_at = datetime.now(timezone.utc)
            self._fail_count += 1
            log.error("publish.failed", error=str(exc))

        return task

    # ------------------------------------------------------------------
    # 5. run_pipeline
    # ------------------------------------------------------------------

    async def run_pipeline(self, language: str = "ja") -> list[dict]:
        """フルパイプライン: plan -> create -> edit -> publish.

        Parameters
        ----------
        language:
            ``"ja"`` or ``"en"``.

        Returns
        -------
        list[dict]
            公開されたコンテンツのサマリーリスト。
        """
        log = logger.bind(pipeline="full", language=language)
        log.info("pipeline.start")
        self._last_run = datetime.now(timezone.utc)

        results: list[dict] = []

        # 1. Plan
        await self._log("info", f"Pipeline started for language={language}", language)
        tasks = await self.plan(language)

        if not tasks:
            log.warning("pipeline.no_tasks")
            await self._log("warning", "No tasks planned", language)
            return results

        # 2-4. Create -> Edit -> Publish (各タスクを順に処理)
        for i, task in enumerate(tasks, 1):
            task_log = log.bind(task_index=i, total_tasks=len(tasks))
            task_log.info("pipeline.task_start")

            # Create
            await self._log("info", f"Creating content {i}/{len(tasks)}", language)
            task = await self.create(task)
            if task.status == "failed":
                task_log.warning("pipeline.create_failed", error=task.error)
                await self._log("error", f"Create failed: {task.error}", language)
                results.append(self._task_summary(task, "create_failed"))
                continue

            # Edit
            await self._log("info", f"Editing content {i}/{len(tasks)}", language)
            task = await self.edit(task)
            if task.status == "failed":
                task_log.warning("pipeline.edit_failed", error=task.error)
                await self._log("error", f"Edit failed: {task.error}", language)
                results.append(self._task_summary(task, "edit_failed"))
                continue

            # Publish
            await self._log("info", f"Publishing content {i}/{len(tasks)}", language)
            task = await self.publish(task)
            if task.status == "failed":
                task_log.warning("pipeline.publish_failed", error=task.error)
                await self._log("error", f"Publish failed: {task.error}", language)
                results.append(self._task_summary(task, "publish_failed"))
                continue

            results.append(self._task_summary(task, "published"))
            task_log.info("pipeline.task_done")

        await self._log(
            "info",
            f"Pipeline completed: {len(results)} items processed",
            language,
        )
        log.info("pipeline.done", total_results=len(results))
        return results

    # ------------------------------------------------------------------
    # 6. run_dual_language_pipeline
    # ------------------------------------------------------------------

    async def run_dual_language_pipeline(self) -> dict:
        """日英両言語のパイプラインを実行する.

        Returns
        -------
        dict
            ``{"ja": [...], "en": [...]}`` 形式の結果。
        """
        logger.info("dual_pipeline.start")

        ja_results = await self.run_pipeline("ja")
        en_results = await self.run_pipeline("en")

        combined = {
            "ja": ja_results,
            "en": en_results,
            "summary": {
                "ja_count": len(ja_results),
                "en_count": len(en_results),
                "total": len(ja_results) + len(en_results),
                "run_at": datetime.now(timezone.utc).isoformat(),
            },
        }

        logger.info(
            "dual_pipeline.done",
            ja_count=len(ja_results),
            en_count=len(en_results),
        )
        return combined

    # ------------------------------------------------------------------
    # 7. get_pipeline_status
    # ------------------------------------------------------------------

    async def get_pipeline_status(self) -> dict:
        """パイプラインの現在のステータスを返す.

        Returns
        -------
        dict
            last_run, success_count, fail_count, recent_logs を含む辞書。
        """
        recent_logs = await self._db.fetch_all(
            """
            SELECT level, message, created_at
            FROM system_logs
            WHERE component = 'brain'
            ORDER BY created_at DESC
            LIMIT 20
            """,
        )

        # 直近の公開コンテンツ
        recent_published = await self._db.fetch_all(
            """
            SELECT id, title, language, quality_score, status, created_at
            FROM contents
            WHERE status = 'published'
            ORDER BY created_at DESC
            LIMIT 10
            """,
        )

        return {
            "last_run": self._last_run.isoformat() if self._last_run else None,
            "success_count": self._success_count,
            "fail_count": self._fail_count,
            "recent_logs": recent_logs,
            "recent_published": recent_published,
        }

    # ==================================================================
    # Private helpers
    # ==================================================================

    async def _rewrite_weak_areas(
        self,
        title: str,
        body: str,
        language: str,
        evaluation: EvaluationResult,
    ) -> tuple[str, str]:
        """評価結果の弱点に基づき、LLM でコンテンツを部分的にリライトする.

        全体を再生成するのではなく、低スコアの観点に焦点を当てて改善する。

        Returns
        -------
        tuple[str, str]
            (改善後の body, 改善後の title)
        """
        # 弱点の特定 (スコアが閾値未満の観点)
        weak_areas: list[str] = []
        threshold = settings.QUALITY_THRESHOLD

        if evaluation.naturalness < threshold:
            weak_areas.append(f"naturalness (score: {evaluation.naturalness})")
        if evaluation.engagement < threshold:
            weak_areas.append(f"engagement (score: {evaluation.engagement})")
        if evaluation.seo_quality < threshold:
            weak_areas.append(f"SEO quality (score: {evaluation.seo_quality})")
        if evaluation.structure < threshold:
            weak_areas.append(f"structure (score: {evaluation.structure})")
        if evaluation.originality < threshold:
            weak_areas.append(f"originality (score: {evaluation.originality})")

        if not weak_areas:
            weak_areas.append("overall quality")

        system_prompt = (
            "You are an expert content editor. Rewrite and improve the given article "
            "focusing specifically on the identified weak areas. "
            "Preserve the core message and factual content. "
            "Do NOT regenerate from scratch -- improve the existing text. "
            "Return a JSON object with keys: \"title\" (string), \"body\" (string)."
        )

        user_prompt = (
            f"Language: {language}\n\n"
            f"Original title: {title}\n\n"
            f"Original body:\n{body}\n\n"
            f"Weak areas to improve: {', '.join(weak_areas)}\n\n"
            f"Evaluator feedback: {evaluation.feedback}\n\n"
            f"Suggestions: {json.dumps(evaluation.suggestions, ensure_ascii=False)}\n\n"
            "Rewrite the article improving these specific areas. "
            "Return ONLY a JSON object with \"title\" and \"body\"."
        )

        try:
            result = await self._llm.generate_json(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.5,
            )
            new_body = result.get("body", body)
            new_title = result.get("title", title)
            logger.info(
                "rewrite.done",
                weak_areas=weak_areas,
                original_length=len(body),
                new_length=len(new_body),
            )
            return new_body, new_title

        except Exception as exc:
            logger.warning("rewrite.failed, using original", error=str(exc))
            return body, title

    async def _generate_metadata(
        self,
        title: str,
        body: str,
        language: str,
    ) -> ContentMetadata:
        """SEO メタデータ + SNS サマリー + FAQ を LLM で生成する.

        Returns
        -------
        ContentMetadata
            生成されたメタデータ。LLM 失敗時はフォールバック値を返す。
        """
        system_prompt = (
            "You are an expert SEO and social media specialist. "
            "Generate metadata for the given article. Return ONLY valid JSON with these exact keys:\n"
            '- "seo_title": optimized page title (max 60 chars)\n'
            '- "seo_description": meta description (max 160 chars)\n'
            '- "seo_keywords": list of 5-8 keywords\n'
            '- "sns": object with:\n'
            '    - "x_post": post for X/Twitter (max 140 chars)\n'
            '    - "note_summary": summary for note platform (max 500 chars)\n'
            '    - "og_description": OG description (max 160 chars)\n'
            '- "faq": array of 3-5 objects with "question" and "answer" keys\n'
        )

        user_prompt = (
            f"Language: {language}\n"
            f"Title: {title}\n"
            f"Body (first 1000 chars): {body[:1000]}\n\n"
            "Generate the metadata JSON."
        )

        try:
            raw = await self._llm.generate_json(
                prompt=user_prompt,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            metadata = ContentMetadata(
                sns=SNSSummary(
                    x_post=raw.get("sns", {}).get("x_post", title[:140]),
                    note_summary=raw.get("sns", {}).get("note_summary", title[:500]),
                    og_description=raw.get("sns", {}).get("og_description", title[:160]),
                ),
                faq=[
                    FAQItem(question=item.get("question", ""), answer=item.get("answer", ""))
                    for item in raw.get("faq", [])
                ],
                seo_title=raw.get("seo_title", title[:60]),
                seo_description=raw.get("seo_description", title[:160]),
                seo_keywords=raw.get("seo_keywords", []),
            )
            logger.info("metadata.generated", seo_title=metadata.seo_title)
            return metadata

        except Exception as exc:
            logger.warning("metadata.generation_failed, using fallback", error=str(exc))
            return ContentMetadata(
                sns=SNSSummary(
                    x_post=title[:140],
                    note_summary=title[:500],
                    og_description=title[:160],
                ),
                faq=[],
                seo_title=title[:60],
                seo_description=title[:160],
                seo_keywords=[],
            )

    @staticmethod
    def _parse_plan_response(raw: str) -> list[dict[str, Any]]:
        """Planner の LLM 応答をパースして計画リストを返す."""
        text = raw.strip()
        # マークダウンコードフェンスを除去
        if text.startswith("```"):
            text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text[: text.rfind("```")]
            text = text.strip()

        data = json.loads(text)
        if isinstance(data, dict):
            # LLM が {"plans": [...]} 形式で返した場合
            for key in ("plans", "topics", "items", "content"):
                if key in data and isinstance(data[key], list):
                    data = data[key]
                    break
            else:
                data = [data]

        if not isinstance(data, list):
            raise ValueError(f"Expected a JSON array, got {type(data).__name__}")

        return data

    @staticmethod
    def _task_summary(task: AgentTask, stage: str) -> dict:
        """タスクからサマリー dict を生成する."""
        content_data = (task.output_data or {}).get("content", {})
        evaluation = (task.output_data or {}).get("evaluation", {})
        return {
            "stage": stage,
            "title": content_data.get("title", "N/A"),
            "category": content_data.get("category", "N/A"),
            "score": evaluation.get("overall_score", 0),
            "content_id": (task.output_data or {}).get("content_id"),
            "final_status": (task.output_data or {}).get("final_status"),
            "error": task.error,
        }

    async def _log(self, level: str, message: str, language: str | None = None) -> None:
        """システムログを DB に記録する."""
        full_message = f"[{language}] {message}" if language else message
        try:
            await self._db.save_system_log(
                level=level.upper(),
                message=full_message,
                component="brain",
            )
        except Exception:
            logger.exception("brain._log failed")

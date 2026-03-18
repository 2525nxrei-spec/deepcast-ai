"""Deepcast Engine — Human-in-the-loop レビュー＆フィードバック管理.

濱田氏による承認がない限りコンテンツは公開されない。
生成→レビュー→承認/修正→公開 のゲートを管理する。
"""

from __future__ import annotations

import json
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import TYPE_CHECKING

import structlog
from pydantic import BaseModel, Field

from config.settings import settings

if TYPE_CHECKING:
    from core.database import DatabaseManager
    from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_ENGINE_ROOT = Path(__file__).resolve().parents[1]
_REVIEWS_DIR = _ENGINE_ROOT / "data" / "reviews"
_PROMPTS_PATH = _ENGINE_ROOT / "config" / "prompts.json"

# ---------------------------------------------------------------------------
# Pydantic models
# ---------------------------------------------------------------------------


class ReviewStatus(str, Enum):
    """レビューステータス."""

    PENDING = "pending"
    IN_REVIEW = "in_review"
    APPROVED = "approved"
    REJECTED = "rejected"
    REVISION_REQUESTED = "revision_requested"


class FeedbackEntry(BaseModel):
    """個別フィードバック項目."""

    category: str  # tone, logic, language, seo, audio, general
    comment: str
    severity: str = "medium"  # low, medium, high


class ReviewSheet(BaseModel):
    """レビューシート — 生成コンテンツの評価用."""

    content_id: int
    title: str
    language: str
    summary: str  # auto-generated summary of the content
    body_preview: str  # first 500 chars
    ai_quality_score: int  # from evaluator
    word_count: int
    has_audio: bool
    audio_path: str | None = None
    # Review fields (to be filled by reviewer)
    overall_impression: str | None = None  # free text
    feedback_items: list[FeedbackEntry] = Field(default_factory=list)
    approved: bool = False
    revision_instructions: str | None = None


class ReviewNotification(BaseModel):
    """レビュー依頼通知."""

    message: str
    content_id: int
    title: str
    language: str
    review_sheet_path: str
    audio_path: str | None = None


# ---------------------------------------------------------------------------
# SQL: レビューテーブル定義
# ---------------------------------------------------------------------------

_SQL_CREATE_REVIEW_TABLES = """
CREATE TABLE IF NOT EXISTS reviews (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id        INTEGER NOT NULL REFERENCES contents(id),
    status            TEXT NOT NULL DEFAULT 'pending'
                      CHECK(status IN ('pending','in_review','approved','rejected','revision_requested')),
    reviewer_name     TEXT DEFAULT '濱田',
    feedback_text     TEXT,
    feedback_category TEXT,
    score             INTEGER,
    revision_notes    TEXT,
    audio_path        TEXT,
    review_sheet_path TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    reviewed_at       TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feedback_log (
    id                INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id        INTEGER REFERENCES contents(id),
    feedback_type     TEXT NOT NULL,
    feedback_text     TEXT NOT NULL,
    applied_to_prompt INTEGER DEFAULT 0,
    language          TEXT,
    created_at        TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# Reviewer
# ---------------------------------------------------------------------------


class Reviewer:
    """Human-in-the-loop review manager.

    Ensures no content is published without explicit approval from 濱田氏.
    Manages the feedback loop for continuous improvement.
    """

    def __init__(self, db: DatabaseManager, llm: LLMClient) -> None:
        self._db = db
        self._llm = llm

    # ------------------------------------------------------------------
    # 0. init_review_tables
    # ------------------------------------------------------------------

    async def init_review_tables(self) -> None:
        """reviews / feedback_log テーブルが存在しなければ作成する."""
        db = await self._db._get_connection()
        await db.executescript(_SQL_CREATE_REVIEW_TABLES)
        await db.commit()
        logger.info("review_tables.initialized")

    # ------------------------------------------------------------------
    # 1. submit_for_review
    # ------------------------------------------------------------------

    async def submit_for_review(
        self,
        content_id: int,
        audio_path: str | None = None,
    ) -> ReviewNotification:
        """コンテンツをレビュー待ちに登録する.

        1. DB からコンテンツを取得
        2. ReviewSheet を自動生成
        3. JSON + Markdown ファイルとして保存
        4. reviews テーブルにレコード作成
        5. コンテンツステータスを 'draft' に更新（レビュー中を示す）
        6. ReviewNotification を返す

        Raises:
            ValueError: content_id が存在しない場合.
        """
        content = await self._db.get_content(content_id)
        if content is None:
            raise ValueError(f"Content ID {content_id} が見つかりません")

        # AI 品質スコアを取得（quality_logs から最新）
        score_rows = await self._db.fetch_all(
            "SELECT score FROM quality_logs WHERE content_id = ? ORDER BY created_at DESC LIMIT 1",
            (content_id,),
        )
        ai_score = score_rows[0]["score"] if score_rows else content.get("quality_score", 0)

        # ReviewSheet を構築
        body_text: str = content.get("body", "")
        summary = await self._generate_summary(body_text, content.get("language", "ja"))

        sheet = ReviewSheet(
            content_id=content_id,
            title=content.get("title", ""),
            language=content.get("language", "ja"),
            summary=summary,
            body_preview=body_text[:500],
            ai_quality_score=ai_score,
            word_count=len(body_text),
            has_audio=audio_path is not None,
            audio_path=audio_path,
        )

        # data/reviews/ ディレクトリを作成
        _REVIEWS_DIR.mkdir(parents=True, exist_ok=True)

        # JSON として保存
        json_path = _REVIEWS_DIR / f"review_{content_id}.json"
        json_path.write_text(
            sheet.model_dump_json(indent=2),
            encoding="utf-8",
        )

        # Markdown として保存
        md_text = await self.generate_review_sheet_md(content, ai_score, audio_path)
        md_path = _REVIEWS_DIR / f"review_{content_id}.md"
        md_path.write_text(md_text, encoding="utf-8")

        # reviews テーブルにレコード作成
        await self._db.execute(
            """
            INSERT INTO reviews
                (content_id, status, audio_path, review_sheet_path)
            VALUES (?, 'pending', ?, ?)
            """,
            (content_id, audio_path, str(md_path)),
        )

        # コンテンツステータスを draft に更新（レビュー待ち）
        await self._db.update_content_status(content_id, "draft")

        logger.info(
            "review.submitted",
            content_id=content_id,
            review_sheet=str(md_path),
        )

        return ReviewNotification(
            message="生成が完了しました。内容の確認と音声の試聴をお願いします。",
            content_id=content_id,
            title=content.get("title", ""),
            language=content.get("language", "ja"),
            review_sheet_path=str(md_path),
            audio_path=audio_path,
        )

    # ------------------------------------------------------------------
    # 2. generate_review_sheet_md
    # ------------------------------------------------------------------

    async def generate_review_sheet_md(
        self,
        content: dict,
        ai_score: int,
        audio_path: str | None,
    ) -> str:
        """人間が読みやすい Markdown レビューシートを生成する."""
        content_id = content.get("id", 0)
        title = content.get("title", "")
        language = content.get("language", "ja")
        body_text: str = content.get("body", "")
        now_str = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")

        # LLM で 3 行要約を生成
        summary = await self._generate_summary(body_text, language)

        audio_display = audio_path if audio_path else "未生成"
        body_preview = body_text[:500]
        if len(body_text) > 500:
            body_preview += "..."

        md = f"""# レビューシート — EP#{content_id}: {title}

## 基本情報
- 言語: {language}
- AI品質スコア: {ai_score}/100
- 文字数: {len(body_text)}
- 音声: {audio_display}
- 生成日時: {now_str}

## コンテンツ要約
{summary}

## 本文プレビュー（先頭500文字）
{body_preview}

---

## 評価項目（ご記入ください）

### 全体の印象
> （自由記述）

### 各項目の評価
| 項目 | 評価 (1-5) | コメント |
|------|-----------|---------|
| トーン・雰囲気 | | |
| 論理の一貫性 | | |
| 日本語/英語の自然さ | | |
| SEO適合性 | | |
| 音声品質 | | |
| エンゲージメント | | |

### 修正指示
> （具体的な修正内容があればご記入ください）

### 判定
- [ ] 承認（このまま公開OK）
- [ ] 要修正（上記修正後に再レビュー）
- [ ] 却下（テーマ変更が必要）
"""
        return md

    # ------------------------------------------------------------------
    # 3. process_feedback
    # ------------------------------------------------------------------

    async def process_feedback(
        self,
        content_id: int,
        feedback_items: list[FeedbackEntry],
        approved: bool,
        revision_instructions: str | None = None,
    ) -> dict:
        """レビュアーからのフィードバックを処理する.

        - 各フィードバック項目を feedback_log に保存
        - review レコードのステータスを更新
        - 承認 → 公開可能に / 修正依頼 → revision_requested
        """
        # コンテンツの言語を取得
        content = await self._db.get_content(content_id)
        language = content.get("language", "ja") if content else "ja"

        # feedback_log に各項目を保存
        for item in feedback_items:
            await self._db.execute(
                """
                INSERT INTO feedback_log
                    (content_id, feedback_type, feedback_text, language)
                VALUES (?, ?, ?, ?)
                """,
                (content_id, item.category, item.comment, language),
            )

        # ステータス決定
        now_str = datetime.now(timezone.utc).isoformat()

        if approved:
            new_status = ReviewStatus.APPROVED
            content_status = "published"
            message = "承認されました。公開準備に入ります。"
        elif revision_instructions:
            new_status = ReviewStatus.REVISION_REQUESTED
            content_status = "draft"
            message = "修正指示を受け付けました。再生成します。"
        else:
            new_status = ReviewStatus.REJECTED
            content_status = "rejected"
            message = "却下されました。テーマ変更を検討します。"

        # reviews テーブルを更新
        feedback_text_combined = "\n".join(
            f"[{item.category}/{item.severity}] {item.comment}"
            for item in feedback_items
        )
        await self._db.execute(
            """
            UPDATE reviews
               SET status = ?,
                   feedback_text = ?,
                   revision_notes = ?,
                   reviewed_at = ?
             WHERE content_id = ?
               AND reviewed_at IS NULL
            """,
            (
                new_status.value,
                feedback_text_combined,
                revision_instructions,
                now_str,
                content_id,
            ),
        )

        # コンテンツステータスを更新
        await self._db.update_content_status(content_id, content_status)

        # システムログ
        await self._db.save_system_log(
            level="INFO",
            message=f"Review {new_status.value} for content_id={content_id}",
            component="reviewer",
        )

        logger.info(
            "review.feedback_processed",
            content_id=content_id,
            status=new_status.value,
            feedback_count=len(feedback_items),
        )

        return {"status": new_status.value, "message": message}

    # ------------------------------------------------------------------
    # 4. apply_feedback_to_prompts
    # ------------------------------------------------------------------

    async def apply_feedback_to_prompts(self, language: str) -> bool:
        """未適用のフィードバックをプロンプトに反映する.

        1. feedback_log から applied_to_prompt=0 のエントリを取得
        2. feedback_type ごとにグルーピング
        3. LLM で「改善制約」を生成
        4. config/prompts.json を更新
        5. applied_to_prompt=1 に更新

        Returns:
            True if prompts were updated.
        """
        # 未適用フィードバックを取得
        rows = await self._db.fetch_all(
            """
            SELECT id, feedback_type, feedback_text
            FROM feedback_log
            WHERE language = ? AND applied_to_prompt = 0
            ORDER BY created_at ASC
            """,
            (language,),
        )

        if not rows:
            logger.info("apply_feedback.no_pending", language=language)
            return False

        # feedback_type ごとにグルーピング
        grouped: dict[str, list[str]] = {}
        feedback_ids: list[int] = []
        for row in rows:
            ft = row["feedback_type"]
            grouped.setdefault(ft, []).append(row["feedback_text"])
            feedback_ids.append(row["id"])

        # LLM で改善制約を生成
        feedback_summary = ""
        for ft, comments in grouped.items():
            feedback_summary += f"\n## {ft}\n"
            for c in comments:
                feedback_summary += f"- {c}\n"

        system_prompt = (
            "あなたはプロンプトエンジニアです。"
            "以下のフィードバックを踏まえ、コンテンツ生成プロンプトに追加すべき"
            "「改善制約」を箇条書きで生成してください。"
            "制約のみを出力し、余計な説明は不要です。"
        )
        user_prompt = (
            f"言語: {language}\n\n"
            f"レビュアーからのフィードバック:\n{feedback_summary}\n\n"
            "これらのフィードバックを踏まえた改善制約を生成してください。"
        )

        constraints = await self._llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        if not constraints or not constraints.strip():
            logger.warning("apply_feedback.empty_constraints", language=language)
            return False

        # prompts.json を更新
        prompt_key = f"{language}_generate"
        try:
            with open(_PROMPTS_PATH, "r", encoding="utf-8") as f:
                prompts = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            logger.error("prompts.json の読み込みに失敗")
            return False

        current_content = prompts.get(prompt_key, {}).get("content", "")
        # フィードバック制約を末尾に追加
        updated_content = (
            current_content.rstrip()
            + "\n\n【レビューフィードバックに基づく追加制約】\n"
            + constraints.strip()
        )
        prompts[prompt_key]["content"] = updated_content

        with open(_PROMPTS_PATH, "w", encoding="utf-8") as f:
            json.dump(prompts, f, ensure_ascii=False, indent=2)

        # applied_to_prompt=1 に更新
        placeholders = ",".join("?" for _ in feedback_ids)
        await self._db.execute(
            f"UPDATE feedback_log SET applied_to_prompt = 1 WHERE id IN ({placeholders})",
            feedback_ids,
        )

        logger.info(
            "apply_feedback.prompts_updated",
            language=language,
            feedback_count=len(rows),
            prompt_key=prompt_key,
        )
        return True

    # ------------------------------------------------------------------
    # 5. get_pending_reviews
    # ------------------------------------------------------------------

    async def get_pending_reviews(self) -> list[dict]:
        """pending / in_review ステータスのレビューを一覧する."""
        rows = await self._db.fetch_all(
            """
            SELECT r.id AS review_id,
                   r.content_id,
                   r.status AS review_status,
                   r.audio_path,
                   r.review_sheet_path,
                   r.created_at,
                   c.title,
                   c.language,
                   c.quality_score AS ai_score
              FROM reviews r
              JOIN contents c ON c.id = r.content_id
             WHERE r.status IN ('pending', 'in_review')
             ORDER BY r.created_at ASC
            """,
        )
        logger.info("pending_reviews.fetched", count=len(rows))
        return rows

    # ------------------------------------------------------------------
    # 6. get_feedback_summary
    # ------------------------------------------------------------------

    async def get_feedback_summary(self, language: str | None = None) -> dict:
        """フィードバックの集計サマリーを返す.

        Returns:
            {
                "total_reviews": int,
                "approval_rate": float,
                "common_feedback": [...],
                "avg_revision_rounds": float,
            }
        """
        # 全レビュー数と承認数
        if language:
            review_rows = await self._db.fetch_all(
                """
                SELECT r.status
                  FROM reviews r
                  JOIN contents c ON c.id = r.content_id
                 WHERE c.language = ?
                """,
                (language,),
            )
        else:
            review_rows = await self._db.fetch_all(
                "SELECT status FROM reviews",
            )

        total_reviews = len(review_rows)
        approved_count = sum(1 for r in review_rows if r["status"] == "approved")
        approval_rate = (approved_count / total_reviews) if total_reviews > 0 else 0.0

        # フィードバックカテゴリ別の集計
        if language:
            feedback_rows = await self._db.fetch_all(
                """
                SELECT feedback_type, COUNT(*) AS cnt
                  FROM feedback_log
                 WHERE language = ?
                 GROUP BY feedback_type
                 ORDER BY cnt DESC
                """,
                (language,),
            )
        else:
            feedback_rows = await self._db.fetch_all(
                """
                SELECT feedback_type, COUNT(*) AS cnt
                  FROM feedback_log
                 GROUP BY feedback_type
                 ORDER BY cnt DESC
                """,
            )

        common_feedback = [
            {"category": r["feedback_type"], "count": r["cnt"]}
            for r in feedback_rows
        ]

        # 平均修正ラウンド数（revision_requested の回数 / ユニークコンテンツ数）
        revision_rows = await self._db.fetch_all(
            "SELECT content_id, COUNT(*) AS rounds FROM reviews WHERE status = 'revision_requested' GROUP BY content_id",
        )
        if revision_rows:
            avg_revision_rounds = sum(r["rounds"] for r in revision_rows) / len(revision_rows)
        else:
            avg_revision_rounds = 0.0

        summary = {
            "total_reviews": total_reviews,
            "approval_rate": round(approval_rate, 4),
            "common_feedback": common_feedback,
            "avg_revision_rounds": round(avg_revision_rounds, 2),
        }

        logger.info("feedback_summary", **summary)
        return summary

    # ------------------------------------------------------------------
    # 7. is_publish_locked
    # ------------------------------------------------------------------

    async def is_publish_locked(self, content_id: int) -> bool:
        """コンテンツが公開ロック状態（未承認）かを返す.

        Publisher が公開前に呼び出す。
        承認レコードが存在しなければ True（ロック中 = 公開不可）。
        """
        rows = await self._db.fetch_all(
            "SELECT id FROM reviews WHERE content_id = ? AND status = 'approved' LIMIT 1",
            (content_id,),
        )
        locked = len(rows) == 0
        logger.debug(
            "publish_lock.checked",
            content_id=content_id,
            locked=locked,
        )
        return locked

    # ------------------------------------------------------------------
    # 8. revise_content
    # ------------------------------------------------------------------

    async def revise_content(self, content_id: int) -> int:
        """フィードバックを踏まえてコンテンツを再生成する.

        1. 元コンテンツとフィードバックを取得
        2. フィードバックを制約として LLM で再生成
        3. 新バージョンとして DB に保存（metadata で元 content_id をリンク）
        4. 自動的にレビュー提出
        5. 新しい content_id を返す

        Raises:
            ValueError: content_id が存在しない場合.
        """
        content = await self._db.get_content(content_id)
        if content is None:
            raise ValueError(f"Content ID {content_id} が見つかりません")

        # フィードバックを取得
        feedback_rows = await self._db.fetch_all(
            """
            SELECT feedback_type, feedback_text
              FROM feedback_log
             WHERE content_id = ?
             ORDER BY created_at DESC
            """,
            (content_id,),
        )

        # 修正指示を取得
        review_rows = await self._db.fetch_all(
            """
            SELECT revision_notes
              FROM reviews
             WHERE content_id = ?
               AND revision_notes IS NOT NULL
             ORDER BY created_at DESC
             LIMIT 1
            """,
            (content_id,),
        )
        revision_notes = review_rows[0]["revision_notes"] if review_rows else ""

        # フィードバックを制約文として組み立て
        constraints: list[str] = []
        for fb in feedback_rows:
            constraints.append(f"- [{fb['feedback_type']}] {fb['feedback_text']}")
        if revision_notes:
            constraints.append(f"- [修正指示] {revision_notes}")

        constraints_text = "\n".join(constraints) if constraints else "特になし"

        language = content.get("language", "ja")
        title = content.get("title", "")
        body = content.get("body", "")

        # LLM で再生成
        system_prompt = (
            "あなたはコンテンツライターです。以下の元記事をレビュアーのフィードバックに基づいて修正してください。"
            "修正後の記事全文のみを出力してください。"
        )
        user_prompt = (
            f"【タイトル】\n{title}\n\n"
            f"【元記事】\n{body}\n\n"
            f"【レビュアーからのフィードバック・修正指示】\n{constraints_text}\n\n"
            "上記フィードバックをすべて反映した修正版の記事全文を出力してください。"
        )

        revised_body = await self._llm.generate(
            prompt=user_prompt,
            system_prompt=system_prompt,
        )

        if not revised_body or not revised_body.strip():
            logger.error("revise_content.empty_response", content_id=content_id)
            raise ValueError("LLM からの再生成結果が空でした")

        # 新バージョンとして保存
        metadata = content.get("metadata") or {}
        if isinstance(metadata, str):
            try:
                metadata = json.loads(metadata)
            except (json.JSONDecodeError, TypeError):
                metadata = {}
        metadata["revised_from"] = content_id
        metadata["revision_round"] = metadata.get("revision_round", 0) + 1

        new_content_id = await self._db.save_content(
            title=title,
            body=revised_body.strip(),
            language=language,
            category=content.get("category"),
            tags=content.get("tags"),
            quality_score=0,
            status="draft",
            topic_source=content.get("topic_source"),
            metadata=metadata,
        )

        logger.info(
            "revise_content.saved",
            original_id=content_id,
            new_id=new_content_id,
            revision_round=metadata["revision_round"],
        )

        # 自動的にレビュー提出
        await self.submit_for_review(new_content_id)

        return new_content_id

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _generate_summary(self, body: str, language: str) -> str:
        """LLM でコンテンツの 3 行要約を生成する."""
        if not body or not body.strip():
            return "（コンテンツが空です）"

        # 長すぎる場合は先頭 2000 文字に制限
        truncated = body[:2000]

        if language == "ja":
            system_prompt = "与えられたテキストを3行で簡潔に要約してください。要約のみ出力してください。"
        else:
            system_prompt = "Summarize the given text in exactly 3 concise lines. Output only the summary."

        try:
            summary = await self._llm.generate(
                prompt=truncated,
                system_prompt=system_prompt,
                temperature=0.3,
            )
            return summary.strip()
        except Exception as exc:
            logger.warning("summary_generation.failed", error=str(exc))
            return body[:200] + "..."

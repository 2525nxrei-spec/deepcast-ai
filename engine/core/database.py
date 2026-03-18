"""Deepcast Engine — SQLite database manager (WAL mode, async)."""

from __future__ import annotations

import json
from difflib import SequenceMatcher
from pathlib import Path

import aiosqlite
import structlog

from config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# SQL: テーブル定義
# ---------------------------------------------------------------------------

_SQL_CREATE_TABLES = """
CREATE TABLE IF NOT EXISTS contents (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT NOT NULL,
    body            TEXT NOT NULL,
    language        TEXT NOT NULL CHECK(language IN ('ja', 'en')),
    category        TEXT,
    tags            TEXT,          -- JSON array
    quality_score   INTEGER DEFAULT 0,
    status          TEXT DEFAULT 'draft'
                    CHECK(status IN ('draft', 'published', 'rejected', 'archived')),
    topic_source    TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    published_at    TIMESTAMP,
    metadata        TEXT           -- JSON
);

CREATE TABLE IF NOT EXISTS quality_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    content_id      INTEGER NOT NULL REFERENCES contents(id),
    score           INTEGER,
    feedback        TEXT,
    evaluator_model TEXT,
    prompt_version  TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS topics (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    title           TEXT,
    language        TEXT,
    category        TEXT,
    keywords        TEXT,          -- JSON array
    status          TEXT DEFAULT 'pending'
                    CHECK(status IN ('pending', 'in_progress', 'completed', 'skipped')),
    priority        INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS prompt_history (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    prompt_type     TEXT,
    prompt_text     TEXT,
    avg_score       REAL,
    usage_count     INTEGER DEFAULT 0,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS system_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    level           TEXT,
    message         TEXT,
    component       TEXT,
    created_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
"""


# ---------------------------------------------------------------------------
# DatabaseManager
# ---------------------------------------------------------------------------


class DatabaseManager:
    """aiosqlite を使った非同期 SQLite マネージャ (WAL モード)."""

    def __init__(self, db_path: str | None = None) -> None:
        self._db_path = db_path or settings.DB_PATH
        self._db: aiosqlite.Connection | None = None

    # ------------------------------------------------------------------
    # connection helpers
    # ------------------------------------------------------------------

    async def _get_connection(self) -> aiosqlite.Connection:
        """既存の接続を返すか、新しく開いて WAL を有効化する."""
        if self._db is None:
            Path(self._db_path).parent.mkdir(parents=True, exist_ok=True)
            self._db = await aiosqlite.connect(self._db_path)
            self._db.row_factory = aiosqlite.Row
            await self._db.execute("PRAGMA journal_mode=WAL")
            await self._db.execute("PRAGMA foreign_keys=ON")
            logger.info("database.connected", path=self._db_path)
        return self._db

    async def close(self) -> None:
        """接続を閉じる."""
        if self._db is not None:
            await self._db.close()
            self._db = None
            logger.info("database.closed")

    # ------------------------------------------------------------------
    # 1. init_db
    # ------------------------------------------------------------------

    async def init_db(self) -> None:
        """テーブルが存在しなければ作成する."""
        db = await self._get_connection()
        await db.executescript(_SQL_CREATE_TABLES)
        await db.commit()
        logger.info("database.initialized")

    # ------------------------------------------------------------------
    # 2. save_content
    # ------------------------------------------------------------------

    async def save_content(
        self,
        title: str,
        body: str,
        language: str,
        category: str | None = None,
        tags: list[str] | None = None,
        quality_score: int = 0,
        status: str = "draft",
        topic_source: str | None = None,
        metadata: dict | None = None,
    ) -> int:
        """コンテンツを保存し、新規 ID を返す."""
        db = await self._get_connection()
        cursor = await db.execute(
            """
            INSERT INTO contents
                (title, body, language, category, tags,
                 quality_score, status, topic_source, metadata)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                title,
                body,
                language,
                category,
                json.dumps(tags) if tags else None,
                quality_score,
                status,
                topic_source,
                json.dumps(metadata) if metadata else None,
            ),
        )
        await db.commit()
        content_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.info("content.saved", content_id=content_id, title=title)
        return content_id

    # ------------------------------------------------------------------
    # 3. get_content
    # ------------------------------------------------------------------

    async def get_content(self, content_id: int) -> dict | None:
        """指定 ID のコンテンツを dict で返す."""
        db = await self._get_connection()
        cursor = await db.execute(
            "SELECT * FROM contents WHERE id = ?", (content_id,)
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return self._row_to_dict(row)

    # ------------------------------------------------------------------
    # 4. list_contents
    # ------------------------------------------------------------------

    async def list_contents(
        self,
        language: str | None = None,
        status: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> list[dict]:
        """条件付きでコンテンツ一覧を返す."""
        clauses: list[str] = []
        params: list = []

        if language is not None:
            clauses.append("language = ?")
            params.append(language)
        if status is not None:
            clauses.append("status = ?")
            params.append(status)

        where = f"WHERE {' AND '.join(clauses)}" if clauses else ""
        sql = f"SELECT * FROM contents {where} ORDER BY created_at DESC LIMIT ? OFFSET ?"
        params += [limit, offset]

        db = await self._get_connection()
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [self._row_to_dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 5. update_content_status
    # ------------------------------------------------------------------

    async def update_content_status(self, content_id: int, status: str) -> None:
        """コンテンツのステータスを更新する."""
        db = await self._get_connection()
        await db.execute(
            """
            UPDATE contents
               SET status = ?, updated_at = CURRENT_TIMESTAMP,
                   published_at = CASE WHEN ? = 'published' THEN CURRENT_TIMESTAMP
                                       ELSE published_at END
             WHERE id = ?
            """,
            (status, status, content_id),
        )
        await db.commit()
        logger.info("content.status_updated", content_id=content_id, status=status)

    # ------------------------------------------------------------------
    # 6. save_quality_log
    # ------------------------------------------------------------------

    async def save_quality_log(
        self,
        content_id: int,
        score: int,
        feedback: str | None = None,
        evaluator_model: str | None = None,
        prompt_version: str | None = None,
    ) -> None:
        """品質ログを保存する."""
        db = await self._get_connection()
        await db.execute(
            """
            INSERT INTO quality_logs
                (content_id, score, feedback, evaluator_model, prompt_version)
            VALUES (?, ?, ?, ?, ?)
            """,
            (content_id, score, feedback, evaluator_model, prompt_version),
        )
        await db.commit()
        logger.info("quality_log.saved", content_id=content_id, score=score)

    # ------------------------------------------------------------------
    # 7. get_quality_trend
    # ------------------------------------------------------------------

    async def get_quality_trend(
        self, language: str, days: int = 7
    ) -> list[dict]:
        """過去 N 日間の言語別平均スコアを日ごとに返す."""
        db = await self._get_connection()
        cursor = await db.execute(
            """
            SELECT DATE(ql.created_at) AS day,
                   CAST(AVG(ql.score) AS INTEGER) AS avg_score,
                   COUNT(*) AS count
              FROM quality_logs ql
              JOIN contents c ON c.id = ql.content_id
             WHERE c.language = ?
               AND ql.created_at >= DATE('now', ?)
             GROUP BY day
             ORDER BY day
            """,
            (language, f"-{days} days"),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 8. save_topic
    # ------------------------------------------------------------------

    async def save_topic(
        self,
        title: str,
        language: str,
        category: str | None = None,
        keywords: list[str] | None = None,
        priority: int = 0,
    ) -> int:
        """トピックを保存し、新規 ID を返す."""
        db = await self._get_connection()
        cursor = await db.execute(
            """
            INSERT INTO topics (title, language, category, keywords, priority)
            VALUES (?, ?, ?, ?, ?)
            """,
            (
                title,
                language,
                category,
                json.dumps(keywords) if keywords else None,
                priority,
            ),
        )
        await db.commit()
        topic_id: int = cursor.lastrowid  # type: ignore[assignment]
        logger.info("topic.saved", topic_id=topic_id, title=title)
        return topic_id

    # ------------------------------------------------------------------
    # 9. get_pending_topics
    # ------------------------------------------------------------------

    async def get_pending_topics(
        self, language: str, limit: int = 5
    ) -> list[dict]:
        """pending 状態のトピックを優先度順で返す."""
        db = await self._get_connection()
        cursor = await db.execute(
            """
            SELECT * FROM topics
             WHERE language = ? AND status = 'pending'
             ORDER BY priority DESC, created_at ASC
             LIMIT ?
            """,
            (language, limit),
        )
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    # ------------------------------------------------------------------
    # 10. update_topic_status
    # ------------------------------------------------------------------

    async def update_topic_status(self, topic_id: int, status: str) -> None:
        """トピックのステータスを更新する."""
        db = await self._get_connection()
        await db.execute(
            "UPDATE topics SET status = ? WHERE id = ?",
            (status, topic_id),
        )
        await db.commit()
        logger.info("topic.status_updated", topic_id=topic_id, status=status)

    # ------------------------------------------------------------------
    # 11. check_duplicate
    # ------------------------------------------------------------------

    async def check_duplicate(
        self, title: str, language: str, threshold: float = 0.8
    ) -> bool:
        """同一言語の既存タイトルとファジー比較し、重複があれば True."""
        db = await self._get_connection()
        cursor = await db.execute(
            "SELECT title FROM contents WHERE language = ?", (language,)
        )
        rows = await cursor.fetchall()
        for row in rows:
            ratio = SequenceMatcher(None, title, row["title"]).ratio()
            if ratio >= threshold:
                logger.info(
                    "duplicate.detected",
                    new_title=title,
                    existing_title=row["title"],
                    ratio=round(ratio, 3),
                )
                return True
        return False

    # ------------------------------------------------------------------
    # 12. save_system_log
    # ------------------------------------------------------------------

    async def save_system_log(
        self, level: str, message: str, component: str | None = None
    ) -> None:
        """システムログを DB に保存する."""
        db = await self._get_connection()
        await db.execute(
            """
            INSERT INTO system_logs (level, message, component)
            VALUES (?, ?, ?)
            """,
            (level, message, component),
        )
        await db.commit()

    # ------------------------------------------------------------------
    # 13. get_prompt_performance
    # ------------------------------------------------------------------

    async def get_prompt_performance(self, prompt_type: str) -> dict | None:
        """指定タイプで最もパフォーマンスの高いプロンプトを返す."""
        db = await self._get_connection()
        cursor = await db.execute(
            """
            SELECT * FROM prompt_history
             WHERE prompt_type = ?
             ORDER BY avg_score DESC, usage_count DESC
             LIMIT 1
            """,
            (prompt_type,),
        )
        row = await cursor.fetchone()
        if row is None:
            return None
        return dict(row)

    # ------------------------------------------------------------------
    # Generic query helpers (for ad-hoc SQL in other modules)
    # ------------------------------------------------------------------

    async def fetch_all(
        self, sql: str, params: tuple | list = ()
    ) -> list[dict]:
        """任意の SELECT を実行し、結果を list[dict] で返す."""
        db = await self._get_connection()
        cursor = await db.execute(sql, params)
        rows = await cursor.fetchall()
        return [dict(r) for r in rows]

    async def execute(
        self, sql: str, params: tuple | list = ()
    ) -> int | None:
        """任意の INSERT / UPDATE / DELETE を実行し、lastrowid を返す."""
        db = await self._get_connection()
        cursor = await db.execute(sql, params)
        await db.commit()
        return cursor.lastrowid

    # ------------------------------------------------------------------
    # helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _row_to_dict(row: aiosqlite.Row) -> dict:
        """Row を dict に変換し、JSON カラムをパースする."""
        d = dict(row)
        for key in ("tags", "keywords", "metadata"):
            if key in d and d[key] is not None:
                try:
                    d[key] = json.loads(d[key])
                except (json.JSONDecodeError, TypeError):
                    pass
        return d

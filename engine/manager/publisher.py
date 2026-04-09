"""Deepcast Engine — Auto-publisher for DeepCast website.

Reads finalized content from the database and deploys it to the
static DeepCast site (episode HTML, episodes.json, sitemap, RSS feed,
service worker cache bust).  Git commit is optional (AUTO_GIT_PUSH).
"""

from __future__ import annotations

import asyncio
import json
import re
import subprocess
from datetime import datetime, timezone, timedelta
from enum import Enum
from pathlib import Path
from textwrap import dedent

import structlog
from pydantic import BaseModel

from config.settings import settings
from core.database import DatabaseManager

logger = structlog.get_logger(__name__)

JST = timezone(timedelta(hours=9))


# ---------------------------------------------------------------------------
# Models
# ---------------------------------------------------------------------------


class PublishTarget(str, Enum):
    WEBSITE = "website"      # Static HTML to DeepCast site
    RSS = "rss"              # RSS feed update
    SITEMAP = "sitemap"      # Sitemap update


class PublishResult(BaseModel):
    target: PublishTarget
    success: bool
    file_path: str | None = None
    error: str | None = None


# ---------------------------------------------------------------------------
# Publisher
# ---------------------------------------------------------------------------


class Publisher:
    """DeepCast サイトへの自動パブリッシャー."""

    def __init__(self, db: DatabaseManager | None = None) -> None:
        self.db = db or DatabaseManager()
        self.site_root = Path(settings.SITE_ROOT)
        self.site_url = settings.SITE_URL

    # ------------------------------------------------------------------
    # 1. publish_episode  (main entry point)
    # ------------------------------------------------------------------

    async def publish_episode(self, content_id: int) -> list[PublishResult]:
        """メインメソッド: DB からコンテンツを取得し全ファイルを生成する."""
        results: list[PublishResult] = []

        content = await self.db.get_content(content_id)
        if content is None:
            logger.error("publish.content_not_found", content_id=content_id)
            results.append(PublishResult(
                target=PublishTarget.WEBSITE,
                success=False,
                error=f"Content ID {content_id} not found",
            ))
            return results

        episode_number = await self.get_next_episode_number()
        logger.info(
            "publish.start",
            content_id=content_id,
            episode_number=episode_number,
            title=content["title"],
        )

        # --- Episode HTML ---
        try:
            html_path = await self.create_episode_html(content, episode_number)
            results.append(PublishResult(
                target=PublishTarget.WEBSITE,
                success=True,
                file_path=html_path,
            ))
        except Exception as exc:
            logger.error("publish.html_failed", error=str(exc))
            results.append(PublishResult(
                target=PublishTarget.WEBSITE,
                success=False,
                error=str(exc),
            ))
            return results  # HTML failure is fatal

        # --- episodes.json ---
        audio_path = content.get("metadata", {}).get("audio_path") if isinstance(content.get("metadata"), dict) else None
        try:
            json_path = await self.update_episodes_json(content, episode_number, audio_path)
            results.append(PublishResult(
                target=PublishTarget.WEBSITE,
                success=True,
                file_path=json_path,
            ))
        except Exception as exc:
            logger.error("publish.json_failed", error=str(exc))
            results.append(PublishResult(
                target=PublishTarget.WEBSITE,
                success=False,
                error=str(exc),
            ))

        # --- Sitemap ---
        try:
            ep_filename = f"ep{episode_number:03d}.html"
            sitemap_path = await self.update_sitemap(f"episodes/{ep_filename}")
            results.append(PublishResult(
                target=PublishTarget.SITEMAP,
                success=True,
                file_path=sitemap_path,
            ))
        except Exception as exc:
            logger.error("publish.sitemap_failed", error=str(exc))
            results.append(PublishResult(
                target=PublishTarget.SITEMAP,
                success=False,
                error=str(exc),
            ))

        # --- RSS Feed ---
        try:
            feed_path = await self.update_feed_xml(content, episode_number, audio_path)
            results.append(PublishResult(
                target=PublishTarget.RSS,
                success=True,
                file_path=feed_path,
            ))
        except Exception as exc:
            logger.error("publish.feed_failed", error=str(exc))
            results.append(PublishResult(
                target=PublishTarget.RSS,
                success=False,
                error=str(exc),
            ))

        # --- Service Worker cache bust ---
        try:
            sw_path = await self.update_service_worker()
            logger.info("publish.sw_updated", path=sw_path)
        except Exception as exc:
            logger.warning("publish.sw_failed", error=str(exc))

        # --- DB status update ---
        await self.db.update_content_status(content_id, "published")

        # --- Git ---
        await self.git_stage_and_commit(content["title"], episode_number)

        # --- Validation ---
        issues = await self.validate_publish(episode_number)
        if issues:
            logger.warning("publish.validation_issues", issues=issues)
        else:
            logger.info("publish.validation_passed", episode_number=episode_number)

        logger.info(
            "publish.complete",
            content_id=content_id,
            episode_number=episode_number,
            results_count=len(results),
            all_success=all(r.success for r in results),
        )
        return results

    # ------------------------------------------------------------------
    # 2. create_episode_html
    # ------------------------------------------------------------------

    async def create_episode_html(self, content: dict, episode_number: int) -> str:
        """既存テンプレートを参考にエピソード HTML を生成する."""
        ep_filename = f"ep{episode_number:03d}.html"
        ep_path = self.site_root / "episodes" / ep_filename
        ep_url = f"{self.site_url}/episodes/{ep_filename}"

        title = content["title"]
        description = content.get("metadata", {}).get("description", "") if isinstance(content.get("metadata"), dict) else ""
        if not description:
            # body の先頭 120 文字をフォールバック
            description = content["body"][:120].replace("\n", " ")

        body_html = content["body"]
        tags = content.get("tags", []) or []
        category = content.get("category", "society") or "society"
        today = datetime.now(JST).strftime("%Y.%m.%d")
        today_iso = datetime.now(JST).strftime("%Y-%m-%d")

        # メタデータからオプション値を取得
        meta = content.get("metadata", {}) if isinstance(content.get("metadata"), dict) else {}
        duration = meta.get("duration", "3:00")
        # tierはepisodes.jsonと一致させる（Single Source of Truth）
        tier = meta.get("tier", "free")
        audio_file = meta.get("audio_path", "")
        keywords = meta.get("keywords", ",".join(tags))
        lead = meta.get("lead", description)

        # audio の相対パス (episodes/ ディレクトリ内なので ../ が必要)
        if audio_file:
            audio_src = f"../{audio_file}" if not audio_file.startswith("../") else audio_file
        else:
            audio_src = ""

        # タグ HTML
        tags_html = "\n        ".join(f'<span class="tag">{t}</span>' for t in tags)

        # カテゴリ表示名マッピング
        category_labels = {
            "society": "社会・文化",
            "technology": "テクノロジー",
            "science": "サイエンス",
            "business": "ビジネス",
            "philosophy": "哲学",
            "education": "教育",
        }
        category_label = category_labels.get(category, category)

        # JSON-LD
        jsonld = json.dumps([
            {
                "@context": "https://schema.org",
                "@type": "PodcastEpisode",
                "name": title,
                "description": description,
                "datePublished": today_iso,
                "duration": f"PT{duration.replace(':', 'M')}S" if ":" in duration else f"PT{duration}",
                "episodeNumber": episode_number,
                "url": ep_url,
                "associatedMedia": {
                    "@type": "MediaObject",
                    "contentUrl": f"{self.site_url}/api/audio/ep{episode_number:03d}",
                },
                "partOfSeries": {
                    "@type": "PodcastSeries",
                    "name": "DeepCast AI",
                    "url": f"{self.site_url}/",
                },
            },
            {
                "@context": "https://schema.org",
                "@type": "BreadcrumbList",
                "itemListElement": [
                    {"@type": "ListItem", "position": 1, "name": "DeepCast AI", "item": f"{self.site_url}/"},
                    {"@type": "ListItem", "position": 2, "name": "エピソード一覧", "item": f"{self.site_url}/all-episodes.html"},
                    {"@type": "ListItem", "position": 3, "name": f"#{episode_number} {title}"},
                ],
            },
        ], ensure_ascii=False, indent=4)

        html = dedent(f"""\
<!DOCTYPE html>
<html lang="ja">
<head>
  <!-- Google Analytics -->
  <script async src="https://www.googletagmanager.com/gtag/js?id=G-NRM2K26K7J"></script>
  <script>
    window.dataLayer = window.dataLayer || [];
    function gtag(){{dataLayer.push(arguments);}}
    gtag('js', new Date());
    gtag('config', 'G-NRM2K26K7J');
  </script>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>#{episode_number} {title}｜DeepCast AI</title>
  <meta name="description" content="{self._escape_attr(description)}">
  <meta name="keywords" content="{self._escape_attr(keywords)}">
  <link rel="canonical" href="{ep_url}">
  <meta property="og:title" content="#{episode_number} {self._escape_attr(title)}｜DeepCast AI">
  <meta property="og:description" content="{self._escape_attr(description)}">
  <meta property="og:type" content="article">
  <meta property="og:url" content="{ep_url}">
  <meta property="og:image" content="{self.site_url}/assets/cover-ep{episode_number:03d}.svg">
  <meta property="og:site_name" content="DeepCast AI">
  <meta property="og:locale" content="ja_JP">
  <meta name="twitter:card" content="summary_large_image">
  <meta name="twitter:title" content="#{episode_number} {self._escape_attr(title)}｜DeepCast AI">
  <meta name="twitter:description" content="{self._escape_attr(description)}">
  <meta name="twitter:image" content="{self.site_url}/assets/cover-ep{episode_number:03d}.svg">
  <link rel="icon" href="../assets/icon.svg" type="image/svg+xml">
  <link rel="apple-touch-icon" href="../assets/icon.svg">
  <link rel="stylesheet" href="../css/style.css">
  <link rel="preconnect" href="https://fonts.googleapis.com">
  <link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
  <link href="https://fonts.googleapis.com/css2?family=Noto+Sans+JP:wght@400;500;600;700&family=Noto+Serif+JP:wght@400;600;700&display=swap" rel="stylesheet">
  <script type="application/ld+json">
  {jsonld}
  </script>
  <style>
    .article-hero {{
      padding: 100px 24px 40px;
      background: var(--bg);
    }}
    .article-hero .container {{ max-width: 760px; margin: 0 auto; }}
    .article-meta {{
      display: flex; align-items: center; gap: 12px; flex-wrap: wrap;
      margin-bottom: 16px; font-size: 12px; color: var(--text-muted);
    }}
    .article-meta .episode-badge {{ padding: 2px 9px; border-radius: var(--radius-full); font-size: 10px; font-weight: 600; background: rgba(94, 194, 105, 0.1); color: var(--green); }}
    .article-hero h1 {{
      font-family: var(--serif);
      font-size: clamp(24px, 4vw, 36px);
      font-weight: 700; line-height: 1.4;
      letter-spacing: -0.02em;
      margin-bottom: 12px;
    }}
    .article-hero .lead {{
      font-size: 15px; color: var(--text-secondary); line-height: 1.8;
    }}
    .article-player-bar {{
      max-width: 760px; margin: 0 auto 32px;
      padding: 16px 24px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      display: flex; align-items: center; gap: 12px;
    }}
    .article-body {{
      max-width: 760px; margin: 0 auto;
      padding: 0 24px 72px;
    }}
    .article-body h2 {{
      font-family: var(--serif);
      font-size: 22px; font-weight: 700;
      margin: 48px 0 16px;
      padding-bottom: 8px;
      border-bottom: 1px solid var(--border);
    }}
    .article-body h3 {{
      font-size: 17px; font-weight: 600;
      margin: 32px 0 12px;
    }}
    .article-body p {{
      font-size: 15px; line-height: 1.9;
      color: var(--text-secondary);
      margin-bottom: 16px;
    }}
    .article-body strong {{ color: var(--text); }}
    .article-body .highlight-box {{
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px 24px;
      margin: 24px 0;
    }}
    .article-body .highlight-box h4 {{
      font-size: 14px; font-weight: 600;
      margin-bottom: 8px; color: var(--text);
    }}
    .article-body .highlight-box ul {{
      list-style: none; padding: 0; margin: 0;
    }}
    .article-body .highlight-box li {{
      font-size: 14px; line-height: 1.7;
      color: var(--text-secondary);
      padding: 4px 0 4px 16px;
      position: relative;
    }}
    .article-body .highlight-box li::before {{
      content: "—"; position: absolute; left: 0; color: var(--text-muted);
    }}
    .article-back {{
      display: inline-flex; align-items: center; gap: 6px;
      font-size: 13px; color: var(--text-muted);
      margin-bottom: 24px;
      transition: color 0.2s;
    }}
    .article-back:hover {{ color: var(--text); }}
    .article-tags {{ display: flex; gap: 6px; margin-top: 8px; }}
    .article-share {{
      margin-top: 48px; padding-top: 24px;
      border-top: 1px solid var(--border);
      text-align: center;
    }}
    .article-share p {{ font-size: 13px; color: var(--text-muted); margin-bottom: 12px; }}
  </style>
</head>
<body data-tier="{tier}">
  <!-- NAVIGATION -->
  <nav class="navbar scrolled" id="navbar">
    <div class="container nav-container">
      <a href="../" class="logo">
        <span class="logo-icon">&#9678;</span>
        <span class="logo-text">DeepCast<span class="logo-ai">AI</span></span>
      </a>
      <ul class="nav-links" id="navLinks">
        <li><a href="../#episodes">エピソード</a></li>
        <li><a href="../#request">リクエスト</a></li>
        <li><a href="../#services">サービス</a></li>
        <li><a href="../#faq">FAQ</a></li>
      </ul>
      <div class="nav-actions">
        <a href="../all-episodes.html" class="btn btn-primary btn-sm">エピソードを聴く</a>
      </div>
      <button class="hamburger" id="hamburger" aria-label="メニュー">
        <span></span><span></span><span></span>
      </button>
    </div>
  </nav>

  <!-- ARTICLE HERO -->
  <div class="article-hero">
    <div class="container">
      <a href="../all-episodes.html" class="article-back">&larr; エピソード一覧に戻る</a>
      <div class="article-meta">
        <span class="episode-badge">FREE</span>
        <span>#{episode_number}</span>
        <span>{today}</span>
        <span>{category_label}</span>
        <span>{duration}</span>
      </div>
      <h1>{title}</h1>
      <p class="lead">{lead}</p>
      <div class="article-tags">
        {tags_html}
      </div>
    </div>
  </div>

  <!-- INLINE PLAYER -->
  <div class="article-player-bar">
    <button class="play-btn" id="articlePlayBtn" data-audio="{audio_src}" data-title="{self._escape_attr(title)}" aria-label="再生">
      <span class="play-icon">&#9654;</span>
    </button>
    <div class="episode-progress" style="flex:1">
      <div class="progress-bar"><div class="progress-fill" id="articleProgressFill" style="width:0%"></div></div>
      <span class="progress-time" id="articleProgressTime">0:00 / {duration}</span>
    </div>
    <span style="font-size:12px;color:var(--text-muted)">音声で聴く</span>
  </div>

  <!-- ARTICLE BODY -->
  <div class="article-body">

    {body_html}

    <div class="article-share">
      <p>このエピソードをシェアする</p>
      <a href="../all-episodes.html" class="btn btn-primary">他のエピソードも聴く</a>
    </div>
  </div>

  <!-- FOOTER -->
  <footer class="footer">
    <div class="container">
      <div class="footer-grid">
        <div class="footer-brand">
          <a href="../" class="logo">
            <span class="logo-icon">&#9678;</span>
            <span class="logo-text">DeepCast<span class="logo-ai">AI</span></span>
          </a>
          <p class="footer-desc">AIが生み出す、5分間の深い洞察。<br>あなたの知識を毎日アップデート。</p>
        </div>
        <div class="footer-links-group">
          <h4>サービス</h4>
          <ul>
            <li><a href="../#episodes">エピソード一覧</a></li>
            <li><a href="../#request">トピックリクエスト</a></li>
          </ul>
        </div>
        <div class="footer-links-group">
          <h4>法的情報</h4>
          <ul>
            <li><a href="../terms.html">利用規約</a></li>
            <li><a href="../privacy.html">プライバシーポリシー</a></li>
            <li><a href="../about.html">運営者情報</a></li>
          </ul>
        </div>
      </div>
      <div class="footer-bottom">
        <p>&copy; 2026 DeepCast AI. All rights reserved.</p>
      </div>
    </div>
  </footer>

  <!-- MINI PLAYER -->
  <div class="mini-player" id="miniPlayer">
    <div class="mini-player-inner">
      <button class="mini-play-btn" id="miniPlayBtn" aria-label="再生/一時停止">
        <span class="play-icon">&#9654;</span>
      </button>
      <div class="mini-info">
        <span class="mini-title" id="miniTitle">-</span>
        <div class="mini-progress-wrap">
          <div class="mini-progress-bar" id="miniProgressBar">
            <div class="mini-progress-fill" id="miniProgressFill" style="width:0%"></div>
          </div>
          <span class="mini-time" id="miniTime">0:00 / 0:00</span>
        </div>
      </div>
      <button class="mini-close-btn" id="miniCloseBtn" aria-label="閉じる">&times;</button>
    </div>
  </div>

  <script src="../js/spa-router.js"></script>
</body>
</html>""")

        ep_path.parent.mkdir(parents=True, exist_ok=True)
        ep_path.write_text(html, encoding="utf-8")
        logger.info("publish.html_created", path=str(ep_path), episode=episode_number)
        return str(ep_path)

    # ------------------------------------------------------------------
    # 3. update_episodes_json
    # ------------------------------------------------------------------

    async def update_episodes_json(
        self,
        content: dict,
        episode_number: int,
        audio_path: str | None = None,
    ) -> str:
        """episodes.json に新エピソードを先頭に追加する."""
        json_file = self.site_root / "episodes" / "episodes.json"
        episodes: list[dict] = []
        if json_file.exists():
            episodes = json.loads(json_file.read_text(encoding="utf-8"))

        # 次の id は既存の最大 + 1
        max_id = max((ep.get("id", 0) for ep in episodes), default=0)
        new_id = max_id + 1

        today = datetime.now(JST).strftime("%Y.%m.%d")
        meta = content.get("metadata", {}) if isinstance(content.get("metadata"), dict) else {}
        tags = content.get("tags", []) or []
        category = content.get("category", "society") or "society"
        duration = meta.get("duration", "3:00")

        # tierはcontentのmetadataから取得、未指定時は"free"（新エピソードはデフォルトfree）
        tier = meta.get("tier", "free")

        new_entry = {
            "id": new_id,
            "title": content["title"],
            "description": meta.get("description", content["body"][:120].replace("\n", " ")),
            "date": today,
            "category": category,
            "tags": tags,
            "duration": duration,
            "audio": audio_path or f"episodes/ep{episode_number:03d}.mp3",
            "article": f"episodes/ep{episode_number:03d}.html",
            "language": content.get("language", "ja"),
            "tier": tier,
        }

        episodes.insert(0, new_entry)
        json_file.write_text(
            json.dumps(episodes, ensure_ascii=False, indent=2) + "\n",
            encoding="utf-8",
        )
        logger.info("publish.episodes_json_updated", new_id=new_id, path=str(json_file))
        return str(json_file)

    # ------------------------------------------------------------------
    # 4. update_sitemap
    # ------------------------------------------------------------------

    async def update_sitemap(self, episode_path: str) -> str:
        """sitemap.xml に新しい URL エントリを追加する."""
        sitemap_file = self.site_root / "sitemap.xml"
        sitemap_text = sitemap_file.read_text(encoding="utf-8")
        today_iso = datetime.now(JST).strftime("%Y-%m-%d")

        new_url_entry = dedent(f"""\
  <url>
    <loc>{self.site_url}/{episode_path}</loc>
    <lastmod>{today_iso}</lastmod>
    <changefreq>yearly</changefreq>
    <priority>0.7</priority>
  </url>""")

        # </urlset> の直前に挿入
        sitemap_text = sitemap_text.replace(
            "</urlset>",
            f"{new_url_entry}\n</urlset>",
        )

        sitemap_file.write_text(sitemap_text, encoding="utf-8")
        logger.info("publish.sitemap_updated", path=str(sitemap_file))
        return str(sitemap_file)

    # ------------------------------------------------------------------
    # 5. update_feed_xml
    # ------------------------------------------------------------------

    async def update_feed_xml(
        self,
        content: dict,
        episode_number: int,
        audio_path: str | None = None,
    ) -> str:
        """feed.xml に新しい <item> を追加する."""
        feed_file = self.site_root / "feed.xml"
        feed_text = feed_file.read_text(encoding="utf-8")

        meta = content.get("metadata", {}) if isinstance(content.get("metadata"), dict) else {}
        tags = content.get("tags", []) or []
        description = meta.get("description", content["body"][:120].replace("\n", " "))
        duration = meta.get("duration", "3:00")
        audio_url = f"{self.site_url}/api/audio/ep{episode_number:03d}"

        # RFC 2822 形式の日付
        now = datetime.now(JST)
        pub_date = now.strftime("%a, %d %b %Y %H:%M:%S +0900")

        keywords_str = ",".join(tags)

        new_item = dedent(f"""\

    <item>
      <title>#{episode_number} {self._escape_xml(content["title"])}</title>
      <description>{self._escape_xml(description)}</description>
      <enclosure url="{audio_url}" type="audio/mpeg" length="0"/>
      <pubDate>{pub_date}</pubDate>
      <itunes:duration>{duration}</itunes:duration>
      <itunes:episode>{episode_number}</itunes:episode>
      <itunes:keywords>{self._escape_xml(keywords_str)}</itunes:keywords>
      <guid isPermaLink="false">deepcast-ep{episode_number:03d}</guid>
    </item>""")

        # 最初の <item> の直前に挿入
        # もし既存 item がなければ </channel> の直前に
        if "<item>" in feed_text:
            first_item_pos = feed_text.index("<item>")
            # その前の改行位置を見つける
            insert_pos = feed_text.rfind("\n", 0, first_item_pos)
            if insert_pos == -1:
                insert_pos = first_item_pos
            feed_text = feed_text[:insert_pos] + new_item + "\n" + feed_text[insert_pos:]
        else:
            feed_text = feed_text.replace(
                "</channel>",
                f"{new_item}\n  </channel>",
            )

        feed_file.write_text(feed_text, encoding="utf-8")
        logger.info("publish.feed_updated", path=str(feed_file))
        return str(feed_file)

    # ------------------------------------------------------------------
    # 6. update_service_worker
    # ------------------------------------------------------------------

    async def update_service_worker(self) -> str:
        """sw.js の CACHE_NAME バージョンをインクリメントする."""
        sw_file = self.site_root / "sw.js"
        sw_text = sw_file.read_text(encoding="utf-8")

        # パターン: 'deepcast-v4' -> 'deepcast-v5'
        match = re.search(r"const CACHE_NAME\s*=\s*['\"]deepcast-v(\d+)['\"]", sw_text)
        if match:
            current_version = int(match.group(1))
            new_version = current_version + 1
            sw_text = sw_text.replace(
                match.group(0),
                f"const CACHE_NAME = 'deepcast-v{new_version}'",
            )
        else:
            logger.warning("publish.sw_version_not_found")

        sw_file.write_text(sw_text, encoding="utf-8")
        logger.info("publish.sw_updated", path=str(sw_file))
        return str(sw_file)

    # ------------------------------------------------------------------
    # 7. get_next_episode_number
    # ------------------------------------------------------------------

    async def get_next_episode_number(self) -> int:
        """episodes.json を読み、最大 id + 1 を返す."""
        json_file = self.site_root / "episodes" / "episodes.json"
        if not json_file.exists():
            return 1
        episodes = json.loads(json_file.read_text(encoding="utf-8"))
        if not episodes:
            return 1
        max_id = max(ep.get("id", 0) for ep in episodes)
        return max_id + 1

    # ------------------------------------------------------------------
    # 8. R2アップロード (wrangler CLI)
    # ------------------------------------------------------------------

    async def upload_to_r2(self, local_path: str, remote_key: str) -> bool:
        """音声ファイルをCloudflare R2にアップロードする.

        Args:
            local_path: ローカルのMP3ファイルパス.
            remote_key: R2上のオブジェクトキー (例: "episodes/ep001.mp3").

        Returns:
            成功した場合True.
        """
        bucket = settings.R2_BUCKET
        logger.info(
            "publish.r2_upload.start",
            local_path=local_path,
            remote_key=remote_key,
            bucket=bucket,
        )

        try:
            proc = await asyncio.create_subprocess_exec(
                "npx", "wrangler", "r2", "object", "put",
                f"{bucket}/{remote_key}",
                "--file", local_path,
                "--content-type", "audio/mpeg",
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode == 0:
                public_url = f"{settings.R2_PUBLIC_URL}/{remote_key}"
                logger.info(
                    "publish.r2_upload.done",
                    remote_key=remote_key,
                    public_url=public_url,
                )
                return True
            else:
                error_msg = stderr.decode(errors="replace")
                logger.error(
                    "publish.r2_upload.failed",
                    returncode=proc.returncode,
                    stderr=error_msg[:500],
                )
                return False
        except Exception as exc:
            logger.error("publish.r2_upload.error", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # 9. git_stage_commit_push (自動デプロイ用)
    # ------------------------------------------------------------------

    async def git_stage_and_commit(
        self, episode_title: str, episode_number: int
    ) -> bool:
        """ブランチを切って変更を git add & commit する.

        masterへの直接pushは禁止のため、autopilot/ep{番号}ブランチを作成する。
        """
        if not settings.AUTO_GIT_PUSH:
            logger.info(
                "publish.git_skipped",
                reason="AUTO_GIT_PUSH is False",
                episode_number=episode_number,
            )
            return False

        try:
            cwd = str(self.site_root)
            branch_name = f"autopilot/ep{episode_number:03d}"
            commit_msg = f"EP#{episode_number}: {episode_title}（自動公開）"

            # masterに戻ってから新ブランチを切る
            proc = await asyncio.create_subprocess_exec(
                "git", "checkout", "master",
                cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            await proc.wait()

            proc = await asyncio.create_subprocess_exec(
                "git", "checkout", "-b", branch_name,
                cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()
            if proc.returncode != 0:
                # ブランチが既に存在する場合は切り替え
                proc = await asyncio.create_subprocess_exec(
                    "git", "checkout", branch_name,
                    cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                )
                await proc.wait()

            self._current_branch = branch_name

            proc_add = await asyncio.create_subprocess_exec(
                "git", "add", "-A",
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            await proc_add.wait()

            proc_commit = await asyncio.create_subprocess_exec(
                "git", "commit", "-m", commit_msg,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc_commit.communicate()

            if proc_commit.returncode == 0:
                logger.info(
                    "publish.git_committed",
                    message=commit_msg,
                    branch=branch_name,
                    episode_number=episode_number,
                )
                return True
            else:
                logger.warning(
                    "publish.git_commit_failed",
                    stderr=stderr.decode(errors="replace"),
                )
                return False
        except Exception as exc:
            logger.error("publish.git_error", error=str(exc))
            return False

    async def git_push(self) -> bool:
        """ブランチをpushしてPRを自動作成する."""
        if not settings.AUTO_GIT_PUSH:
            logger.info("publish.git_push_skipped", reason="AUTO_GIT_PUSH is False")
            return False

        branch = getattr(self, "_current_branch", None)
        if not branch:
            logger.warning("publish.git_push_skipped", reason="no branch set")
            return False

        try:
            cwd = str(self.site_root)

            # ブランチをpush
            proc = await asyncio.create_subprocess_exec(
                "git", "push", "-u", "origin", branch,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            stdout, stderr = await proc.communicate()

            if proc.returncode != 0:
                logger.error(
                    "publish.git_push.failed",
                    stderr=stderr.decode(errors="replace"),
                )
                return False

            logger.info("publish.git_push.done", branch=branch)

            # gh CLIでPR作成
            pr_title = branch.replace("autopilot/", "Autopilot: ").upper()
            proc_pr = await asyncio.create_subprocess_exec(
                "gh", "pr", "create",
                "--title", pr_title,
                "--body", "Autopilotによる自動エピソード公開。CIパス後にマージしてください。",
                "--base", "master",
                "--head", branch,
                cwd=cwd,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
            pr_stdout, pr_stderr = await proc_pr.communicate()

            if proc_pr.returncode == 0:
                pr_url = pr_stdout.decode(errors="replace").strip()
                logger.info("publish.pr_created", url=pr_url)
            else:
                # PR作成失敗はpush成功に影響しない（手動でPR作成可能）
                logger.warning(
                    "publish.pr_create_failed",
                    stderr=pr_stderr.decode(errors="replace"),
                )

            # masterに戻る
            proc = await asyncio.create_subprocess_exec(
                "git", "checkout", "master",
                cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            )
            await proc.wait()

            return True
        except Exception as exc:
            logger.error("publish.git_push.error", error=str(exc))
            return False

    # ------------------------------------------------------------------
    # 9. validate_publish
    # ------------------------------------------------------------------

    async def validate_publish(self, episode_number: int) -> list[str]:
        """公開後バリデーション。問題があればリストで返す (空 = OK)."""
        issues: list[str] = []
        ep_filename = f"ep{episode_number:03d}.html"

        # a. Episode HTML exists and basic validity
        ep_path = self.site_root / "episodes" / ep_filename
        if not ep_path.exists():
            issues.append(f"Episode HTML not found: {ep_path}")
        else:
            html_text = ep_path.read_text(encoding="utf-8")
            if len(html_text) < 3000:
                issues.append(f"Episode HTML is too short ({len(html_text)} chars, expected 3000+)")
            # e. Check for bad href="index.html" pattern
            if 'href="index.html"' in html_text or "href='index.html'" in html_text:
                issues.append("Episode HTML contains href=\"index.html\" — should use href=\"./\"")
            if 'href="../index.html"' in html_text or "href='../index.html'" in html_text:
                issues.append("Episode HTML contains href=\"../index.html\" — should use href=\"../\"")

        # b. episodes.json contains new episode
        json_file = self.site_root / "episodes" / "episodes.json"
        if json_file.exists():
            episodes = json.loads(json_file.read_text(encoding="utf-8"))
            article_key = f"episodes/{ep_filename}"
            found = any(ep.get("article") == article_key for ep in episodes)
            if not found:
                issues.append(f"episodes.json does not contain entry for {article_key}")
        else:
            issues.append("episodes.json not found")

        # c. sitemap.xml contains the new URL
        sitemap_file = self.site_root / "sitemap.xml"
        if sitemap_file.exists():
            sitemap_text = sitemap_file.read_text(encoding="utf-8")
            ep_url = f"{self.site_url}/episodes/{ep_filename}"
            if ep_url not in sitemap_text:
                issues.append(f"sitemap.xml does not contain {ep_url}")
        else:
            issues.append("sitemap.xml not found")

        # d. feed.xml contains the new item
        feed_file = self.site_root / "feed.xml"
        if feed_file.exists():
            feed_text = feed_file.read_text(encoding="utf-8")
            guid = f"deepcast-ep{episode_number:03d}"
            if guid not in feed_text:
                issues.append(f"feed.xml does not contain guid {guid}")
        else:
            issues.append("feed.xml not found")

        return issues

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _escape_attr(text: str) -> str:
        """HTML 属性値用エスケープ."""
        return (
            text.replace("&", "&amp;")
            .replace('"', "&quot;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
        )

    @staticmethod
    def _escape_xml(text: str) -> str:
        """XML テキスト用エスケープ."""
        return (
            text.replace("&", "&amp;")
            .replace("<", "&lt;")
            .replace(">", "&gt;")
            .replace('"', "&quot;")
            .replace("'", "&apos;")
        )

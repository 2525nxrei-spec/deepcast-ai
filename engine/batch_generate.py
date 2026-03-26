"""トピックからエピソードを一括生成するスクリプト.

コンテンツ生成（Gemini）→ 音声生成（Gemini TTS）→ HTML/JSON/XML更新 → R2アップロード
"""
import asyncio
import json
import sqlite3
import shutil
import os
import re
import boto3
from pathlib import Path
from datetime import datetime

from config.settings import settings
from core.voice_engine import VoiceEngine
from core.llm_client import LLMClient
from dotenv import load_dotenv

load_dotenv()

SITE_DIR = Path(settings.SITE_ROOT)
EPISODES_DIR = SITE_DIR / "episodes"
EPISODES_JSON = EPISODES_DIR / "episodes.json"

# 生成対象のトピックID（日本語の魅力的なテーマを優先）
TARGET_TOPICS = [
    13,  # なぜ独裁国家ほどAI開発に積極的なのか
    15,  # スマホを見た瞬間に集中力が死ぬ科学的メカニズム
    19,  # なぜ陰謀論を信じる人は"頭が悪い"わけではないのか
    22,  # なぜ人は"確実に損する"とわかっている宝くじを買い続けるのか
    28,  # トロッコ問題をAIに解かせたら、文化によって答えが違った
    14,  # 半導体チップ1枚が核兵器より強い時代
    16,  # ローマ帝国の崩壊とアメリカの現在が不気味に一致している件
    24,  # 海底ケーブルを切断すれば国が滅ぶ
]


async def generate_content(llm: LLMClient, topic_title: str) -> str:
    """Gemini APIで記事本文を生成"""
    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""以下のテーマについて、ポッドキャスト配信用の記事本文を日本語で書いてください。

テーマ: {topic_title}

要件:
- 1500〜2000文字の記事（長すぎず短すぎず）
- h2見出しを3-5個使用
- 事実に基づいた深い考察
- 読者を引きつける導入
- 具体的なデータや事例を含める
- 結論で新しい視点を提示
- HTMLタグは使わず、プレーンテキストで
"""

    def _gen():
        response = client.models.generate_content(
            model="gemini-2.5-flash",
            contents=prompt,
        )
        return response.text

    return await asyncio.to_thread(_gen)


def get_next_episode_number() -> int:
    """episodes.jsonから次のエピソード番号を取得"""
    with open(EPISODES_JSON, "r", encoding="utf-8") as f:
        episodes = json.load(f)
    max_id = max(ep["id"] for ep in episodes) if episodes else 0
    return max_id + 1


def create_episode_html(ep_num: int, title: str, body: str, description: str) -> Path:
    """エピソードHTMLページを生成（ep001.htmlをテンプレートに）"""
    template_path = EPISODES_DIR / "ep001.html"
    template = template_path.read_text(encoding="utf-8")

    ep_str = f"ep{ep_num:03d}"
    today = datetime.now().strftime("%Y-%m-%d")
    today_dot = datetime.now().strftime("%Y.%m.%d")

    # h2見出しで本文を構造化
    sections = body.split("\n\n")
    article_html = ""
    for section in sections:
        section = section.strip()
        if not section:
            continue
        if section.startswith("## "):
            heading = section.replace("## ", "").strip()
            article_html += f'<h2>{heading}</h2>\n'
        elif section.startswith("### "):
            heading = section.replace("### ", "").strip()
            article_html += f'<h3>{heading}</h3>\n'
        else:
            # 段落
            article_html += f'<p>{section}</p>\n'

    # テンプレートのメタデータを置換
    html = template
    # title
    html = re.sub(r'<title>.*?</title>', f'<title>#{ep_num} {title}｜DeepCast AI</title>', html)
    # meta description
    html = re.sub(r'<meta name="description" content=".*?"', f'<meta name="description" content="{description[:160]}"', html)
    # canonical
    html = re.sub(r'<link rel="canonical" href=".*?"', f'<link rel="canonical" href="https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    # og:title
    html = re.sub(r'<meta property="og:title" content=".*?"', f'<meta property="og:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    # og:description
    html = re.sub(r'<meta property="og:description" content=".*?"', f'<meta property="og:description" content="{description[:160]}"', html)
    # og:url
    html = re.sub(r'<meta property="og:url" content=".*?"', f'<meta property="og:url" content="https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    # twitter:title
    html = re.sub(r'<meta name="twitter:title" content=".*?"', f'<meta name="twitter:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    # twitter:description
    html = re.sub(r'<meta name="twitter:description" content=".*?"', f'<meta name="twitter:description" content="{description[:160]}"', html)

    # article-body の中身を置換
    html = re.sub(
        r'(<div class="article-body">).*?(</div>\s*</article>)',
        rf'\1\n{article_html}\n\2',
        html,
        flags=re.DOTALL,
    )

    # BreadcrumbList の更新
    html = re.sub(
        r'"name":"#\d+ .*?"',
        f'"name":"#{ep_num} {title}"',
        html,
    )

    # PodcastEpisode の更新
    html = re.sub(r'"episodeNumber":\s*\d+', f'"episodeNumber": {ep_num}', html)
    html = re.sub(r'"datePublished":\s*"[^"]*"', f'"datePublished": "{today}"', html)
    html = re.sub(r'"name":\s*"[^"]*"(,\s*"url":\s*"https://deepcast-ai\.com/episodes/)', f'"name": "#{ep_num} {title}"\\1', html)
    html = re.sub(r'"url":\s*"https://deepcast-ai\.com/episodes/ep\d+\.html"', f'"url": "https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'"contentUrl":\s*"[^"]*"', f'"contentUrl": "https://audio.deepcast-ai.com/{ep_str}.mp3"', html)

    out_path = EPISODES_DIR / f"{ep_str}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def update_episodes_json(ep_num: int, title: str, description: str, duration: str, category: str, tags: list[str]):
    """episodes.jsonに新エピソードを追加"""
    with open(EPISODES_JSON, "r", encoding="utf-8") as f:
        episodes = json.load(f)

    ep_str = f"ep{ep_num:03d}"
    today = datetime.now().strftime("%Y.%m.%d")

    new_entry = {
        "id": ep_num,
        "title": title,
        "description": description,
        "date": today,
        "category": category,
        "tags": tags,
        "duration": duration,
        "audio": f"https://audio.deepcast-ai.com/{ep_str}.mp3",
        "article": f"episodes/{ep_str}.html",
        "language": "ja",
    }

    episodes.insert(0, new_entry)

    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(episodes, f, ensure_ascii=False, indent=2)


def upload_to_r2(ep_str: str):
    """音声ファイルをR2にアップロード"""
    s3 = boto3.client(
        "s3",
        endpoint_url=os.environ["R2_ENDPOINT"],
        aws_access_key_id=os.environ["R2_ACCESS_KEY_ID"],
        aws_secret_access_key=os.environ["R2_SECRET_ACCESS_KEY"],
        region_name="auto",
    )
    local_path = str(EPISODES_DIR / f"{ep_str}.mp3")
    s3.upload_file(local_path, "deepcast-audio", f"{ep_str}.mp3", ExtraArgs={"ContentType": "audio/mpeg"})


async def process_topic(topic_id: int, topic_title: str, llm: LLMClient, engine: VoiceEngine):
    """1つのトピックを完全処理"""
    ep_num = get_next_episode_number()
    ep_str = f"ep{ep_num:03d}"

    print(f"\n{'='*60}")
    print(f"[{ep_str}] {topic_title}")
    print(f"{'='*60}")

    # 1. コンテンツ生成
    print("  [1/5] コンテンツ生成中...")
    body = await generate_content(llm, topic_title)
    print(f"  → {len(body)}文字")

    # 説明文を生成（最初の150文字程度）
    description = body[:200].replace("\n", " ").strip()
    if len(description) > 150:
        description = description[:150] + "..."

    # 2. 音声生成
    print("  [2/5] 音声生成中...")
    audio_path = await engine.synthesize_podcast(title=topic_title, body=body, language="ja")
    dest = EPISODES_DIR / f"{ep_str}.mp3"
    shutil.copy2(str(audio_path), str(dest))
    print(f"  → {dest}")

    # 音声の長さを推定（ファイルサイズから。256kbps = 32KB/s）
    file_size = dest.stat().st_size
    duration_sec = file_size / 32000
    minutes = int(duration_sec // 60)
    seconds = int(duration_sec % 60)
    duration_str = f"{minutes}:{seconds:02d}"

    # 3. HTML生成
    print("  [3/5] HTMLページ生成中...")
    create_episode_html(ep_num, topic_title, body, description)

    # 4. episodes.json更新
    print("  [4/5] episodes.json更新中...")
    category = "tech" if any(w in topic_title for w in ["AI", "半導体", "量子", "スマホ", "SNS"]) else "society"
    tags = [t.strip() for t in topic_title.replace("—", "").replace("―", "").split("　") if t.strip()][:4]
    update_episodes_json(ep_num, topic_title, description, duration_str, category, tags)

    # 5. R2アップロード
    print("  [5/5] R2アップロード中...")
    upload_to_r2(ep_str)

    print(f"  [DONE] {ep_str}: {topic_title} ({duration_str})")

    # DB更新: トピックをused、コンテンツをpublished
    conn = sqlite3.connect("data/deepcast.db")
    conn.execute("UPDATE topics SET status = 'used' WHERE id = ?", (topic_id,))
    conn.commit()
    conn.close()

    return ep_num


async def main():
    llm = LLMClient()
    engine = VoiceEngine()

    conn = sqlite3.connect("data/deepcast.db")
    topics = []
    for tid in TARGET_TOPICS:
        row = conn.execute("SELECT id, title FROM topics WHERE id = ? AND status = 'pending'", (tid,)).fetchone()
        if row:
            topics.append((row[0], row[1]))
    conn.close()

    print(f"生成対象: {len(topics)}本")
    generated = 0

    for topic_id, topic_title in topics:
        try:
            await process_topic(topic_id, topic_title, llm, engine)
            generated += 1
            # API制限防止: エピソード間に5秒待機
            await asyncio.sleep(5)
        except Exception as e:
            print(f"  [ERROR] {topic_title}: {e}")
            import traceback
            traceback.print_exc()
            # エラーが出たら次のエピソードへ
            continue

    print(f"\n{'='*60}")
    print(f"完了: {generated}/{len(topics)}本生成")


if __name__ == "__main__":
    asyncio.run(main())

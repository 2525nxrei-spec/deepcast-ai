"""新規エピソード一括生成スクリプト.

Gemini APIでコンテンツ生成 → Gemini TTS で音声合成 → HTML/JSON更新 → R2アップロード
既存エピソードを削除して新規10エピソードを生成する
"""
import asyncio
import io
import json
import shutil
import os
import re
import sys
import traceback
import boto3
from pathlib import Path
from datetime import datetime

# Windows cp932対策: stdoutをUTF-8に変更
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

from config.settings import settings
from core.voice_engine import VoiceEngine
from dotenv import load_dotenv

load_dotenv()

SITE_DIR = Path(settings.SITE_ROOT)
EPISODES_DIR = SITE_DIR / "episodes"
EPISODES_JSON = EPISODES_DIR / "episodes.json"

# 新規生成するトピック（AI・テクノロジー関連、2分30秒の音声向け）
NEW_TOPICS = [
    "AIが書いた論文を見抜けない — 学術界を揺るがす生成AIの衝撃",
    "量子コンピュータが暗号を破る日 — いつ来るのか、どう備えるか",
    "脳とAIの境界線 — ニューラリンクが開く人間拡張の未来",
    "SNSアルゴリズムが選挙を動かす — デジタル民主主義の光と影",
    "なぜGAFAMは宇宙開発に巨額投資するのか — テック企業の宇宙戦略",
    "自動運転車の「トロッコ問題」 — AIに命の選択を任せられるか",
    "ディープフェイクが変える情報戦 — 真実を見極める時代の終わり",
    "電子ゴミが地球を覆う — テクノロジーの裏にある環境コスト",
    "AIが医師を超える日 — 診断精度99%の衝撃と残る課題",
    "プログラミング不要の時代 — ノーコード革命は本物か幻か",
]


async def generate_content(topic_title: str, max_retries: int = 5) -> str:
    """Gemini APIで記事本文を生成（リトライ付き）"""
    import time
    from google import genai
    client = genai.Client(api_key=settings.GEMINI_API_KEY)

    prompt = f"""以下のテーマについて、ポッドキャスト配信用の記事本文を日本語で書いてください。

テーマ: {topic_title}

要件:
- 800〜1200文字程度の記事（2分30秒の音声に適した長さ）
- h2見出しを2-3個使用
- 事実に基づいた深い考察
- 読者を引きつける導入
- 具体的なデータや事例を含める
- 結論で新しい視点を提示
- HTMLタグは使わず、プレーンテキストで
- マークダウン記法（##）で見出しを書く
"""

    def _gen():
        for attempt in range(max_retries):
            try:
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=prompt,
                )
                return response.text
            except Exception as e:
                wait = (attempt + 1) * 10  # 10秒, 20秒, 30秒...
                print(f"    [RETRY {attempt+1}/{max_retries}] {e} — {wait}秒後にリトライ")
                time.sleep(wait)
        raise RuntimeError(f"{max_retries}回リトライしたが失敗: {topic_title}")

    return await asyncio.to_thread(_gen)


def get_next_episode_number() -> int:
    """episodes.jsonから次のエピソード番号を取得"""
    if not EPISODES_JSON.exists():
        return 1
    with open(EPISODES_JSON, "r", encoding="utf-8") as f:
        episodes = json.load(f)
    if not episodes:
        return 1
    max_id = max(ep["id"] for ep in episodes)
    return max_id + 1


_TEMPLATE_HTML = ""  # main()で読み込まれる


def _generate_default_template() -> str:
    """テンプレートファイルが存在しない場合のデフォルトHTML"""
    return '''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Episode｜DeepCast AI</title>
<meta name="description" content="">
<link rel="canonical" href="https://deepcast-ai.com/episodes/ep001.html">
<meta property="og:title" content="Episode｜DeepCast AI">
<meta property="og:description" content="">
<meta property="og:url" content="https://deepcast-ai.com/episodes/ep001.html">
<meta name="twitter:title" content="Episode｜DeepCast AI">
<meta name="twitter:description" content="">
<link rel="stylesheet" href="/assets/css/style.css">
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"BreadcrumbList","itemListElement":[{"@type":"ListItem","position":1,"name":"DeepCast AI","item":"https://deepcast-ai.com/"},{"@type":"ListItem","position":2,"name":"#1 Episode","item":"https://deepcast-ai.com/episodes/ep001.html"}]}
</script>
<script type="application/ld+json">
{"@context":"https://schema.org","@type":"PodcastEpisode","episodeNumber": 1,"datePublished": "2026-03-27","name": "#1 Episode","url": "https://deepcast-ai.com/episodes/ep001.html","associatedMedia":{"@type":"MediaObject","contentUrl": "https://audio.deepcast-ai.com/ep001.mp3"}}
</script>
</head>
<body>
<header class="site-header">
<nav><a href="/">DeepCast AI</a></nav>
</header>
<main>
<article class="episode-detail">
<div class="article-body">
</div>
</article>
</main>
<footer><p>&copy; 2026 DeepCast AI</p></footer>
<script src="/assets/js/auth.js"></script>
</body>
</html>'''

def create_episode_html(ep_num: int, title: str, body: str, description: str) -> Path:
    """エピソードHTMLページを生成（ep001.htmlをテンプレートに）"""
    template = _TEMPLATE_HTML

    ep_str = f"ep{ep_num:03d}"
    today = datetime.now().strftime("%Y-%m-%d")

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
            article_html += f'<p>{section}</p>\n'

    # テンプレートのメタデータを置換
    html = template
    html = re.sub(r'<title>.*?</title>', f'<title>#{ep_num} {title}｜DeepCast AI</title>', html)
    html = re.sub(r'<meta name="description" content=".*?"', f'<meta name="description" content="{description[:160]}"', html)
    html = re.sub(r'<link rel="canonical" href=".*?"', f'<link rel="canonical" href="https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'<meta property="og:title" content=".*?"', f'<meta property="og:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    html = re.sub(r'<meta property="og:description" content=".*?"', f'<meta property="og:description" content="{description[:160]}"', html)
    html = re.sub(r'<meta property="og:url" content=".*?"', f'<meta property="og:url" content="https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'<meta name="twitter:title" content=".*?"', f'<meta name="twitter:title" content="#{ep_num} {title}｜DeepCast AI"', html)
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


def update_episodes_json(ep_num: int, title: str, description: str, duration: str, category: str, tags: list[str], tier: str = "free"):
    """episodes.jsonに新エピソードを追加"""
    if EPISODES_JSON.exists():
        with open(EPISODES_JSON, "r", encoding="utf-8") as f:
            episodes = json.load(f)
    else:
        episodes = []

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
        "tier": tier,
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


async def process_topic(index: int, topic_title: str, engine: VoiceEngine, total: int):
    """1つのトピックを完全処理"""
    ep_num = get_next_episode_number()
    ep_str = f"ep{ep_num:03d}"

    # Free/Pro判定: 最新3つ（最後に生成される3つ）がFree、残りがPro
    # indexは0始まり。total-3以降がFree
    tier = "free" if index >= (total - 3) else "pro"

    print(f"\n{'='*60}")
    print(f"[{ep_str}] ({index+1}/{total}) {topic_title} [{tier.upper()}]")
    print(f"{'='*60}")

    # 1. コンテンツ生成
    print("  [1/5] コンテンツ生成中...")
    body = await generate_content(topic_title)
    print(f"  -> {len(body)}文字")

    # 説明文を生成
    description = body[:200].replace("\n", " ").strip()
    if len(description) > 150:
        description = description[:150] + "..."

    # 2. 音声生成
    print("  [2/5] 音声生成中...")
    audio_path = await engine.synthesize_podcast(title=topic_title, body=body, language="ja")
    dest = EPISODES_DIR / f"{ep_str}.mp3"
    shutil.copy2(str(audio_path), str(dest))
    print(f"  -> {dest}")

    # 音声の長さを推定
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
    category = "tech"
    tags = [w.strip() for w in topic_title.replace("—", " ").replace("―", " ").split() if len(w.strip()) > 1][:4]
    update_episodes_json(ep_num, topic_title, description, duration_str, category, tags, tier)

    # 5. R2アップロード
    print("  [5/5] R2アップロード中...")
    try:
        upload_to_r2(ep_str)
        print(f"  -> R2アップロード完了")
    except Exception as e:
        print(f"  -> R2アップロード失敗: {e}")

    print(f"  [DONE] {ep_str}: {topic_title} ({duration_str}) [{tier.upper()}]")
    return ep_num


async def main():
    engine = VoiceEngine()

    # テンプレートを読み込み（削除前に）
    global _TEMPLATE_HTML
    template_path = EPISODES_DIR / "ep001.html"
    if template_path.exists():
        _TEMPLATE_HTML = template_path.read_text(encoding="utf-8")
        print(f"テンプレート読み込み完了: {len(_TEMPLATE_HTML)}文字")
    else:
        # テンプレートが削除済みの場合、デフォルトHTMLを使用
        print("テンプレートが見つからないためデフォルトHTMLを使用")
        _TEMPLATE_HTML = _generate_default_template()

    # 既存のepisodes.jsonをリセット
    print("既存のepisodes.jsonをリセット...")
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump([], f)

    # 既存のep001〜ep006のHTMLとMP3も削除
    print("既存のエピソードファイルを削除...")
    for i in range(1, 20):
        ep_str = f"ep{i:03d}"
        for ext in [".html", ".mp3"]:
            fp = EPISODES_DIR / f"{ep_str}{ext}"
            if fp.exists():
                fp.unlink()
                print(f"  削除: {fp.name}")

    total = len(NEW_TOPICS)
    print(f"\n生成対象: {total}本")
    print(f"  Free: 最新3本 (ep{total-2:03d}〜ep{total:03d})")
    print(f"  Pro: 残り{total-3}本 (ep001〜ep{total-3:03d})")
    generated = 0

    for i, topic_title in enumerate(NEW_TOPICS):
        try:
            await process_topic(i, topic_title, engine, total)
            generated += 1
            # API制限防止
            await asyncio.sleep(3)
        except Exception as e:
            print(f"  [ERROR] {topic_title}: {e}")
            traceback.print_exc()
            continue

    print(f"\n{'='*60}")
    print(f"完了: {generated}/{total}本生成")

    # 最終的なepisodes.jsonの確認
    with open(EPISODES_JSON, "r", encoding="utf-8") as f:
        episodes = json.load(f)
    print(f"episodes.json: {len(episodes)}件")
    for ep in episodes:
        print(f"  #{ep['id']} [{ep.get('tier', 'free')}] {ep['title']} ({ep['duration']})")


if __name__ == "__main__":
    asyncio.run(main())

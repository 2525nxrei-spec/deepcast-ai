"""Edge-TTS版エピソード一括生成スクリプト.

Gemini APIでコンテンツ＆台本生成 → Edge-TTSで音声合成 → HTML/JSON更新 → R2アップロード
Gemini TTSがハングする問題の回避策としてEdge-TTSを使用。
"""
import asyncio
import io
import json
import os
import re
import sys
import traceback
import time
import subprocess
import hashlib
from pathlib import Path
from datetime import datetime

# Windows cp932対策
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import edge_tts
import boto3
from dotenv import load_dotenv

load_dotenv()

# 設定値
GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_ACCESS_KEY_ID = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_ACCESS_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = os.environ.get("R2_BUCKET", "deepcast-audio")

SITE_DIR = Path(os.environ.get("SITE_ROOT", "G:/マイドライブ/株式会社　礼/運用中/8_ディープキャスト"))
EPISODES_DIR = SITE_DIR / "episodes"
EPISODES_JSON = EPISODES_DIR / "episodes.json"
AUDIO_DIR = Path("./data/audio")
AUDIO_DIR.mkdir(parents=True, exist_ok=True)

# Edge-TTS ボイス設定（日本語、山口＝男性低め、田中＝男性高め）
VOICE_YAMAGUCHI = "ja-JP-KeitaNeural"  # 落ち着いた男性
VOICE_TANAKA = "ja-JP-NanamiNeural"    # 明るい声（女性だが他に選択肢少ない）

# 生成するトピック
TOPICS = [
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

# 台本プロンプト
PODCAST_SCRIPT_PROMPT = """あなたは日本語ラジオ番組の台本ライターです。
【絶対ルール】出力は必ず日本語のみ。英語で書くのは禁止。
【形式】2人のパーソナリティ（山口と田中）の対話形式で書く。
- 山口（男性、渋めの40代）：メインホスト。話題を振り、深掘りする役。
- 田中（男性、明るい20代）：アシスタント。リスナー目線で質問したり、驚いたり共感する役。

【重要：長さの指定】
- 必ず2分30秒〜3分で読み上げられる長さにする
- これはおよそ600〜800文字の台本に相当する
- 短すぎず長すぎず、この範囲を厳守すること

【口調のルール】
- 丁寧だけど堅すぎない口調（「ですます」調ベース）
- 専門用語は対話の中で自然に説明する

【フォーマット】
山口: セリフ
田中: セリフ
の形式で書く。"""


async def call_gemini(prompt: str, timeout: float = 120.0) -> str:
    """httpxで直接Gemini REST APIを呼び出す（タイムアウト付き）"""
    import httpx
    url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash-lite:generateContent?key={GEMINI_API_KEY}"
    payload = {
        "contents": [{"parts": [{"text": prompt}]}],
        "generationConfig": {"temperature": 0.7, "maxOutputTokens": 4096}
    }
    async with httpx.AsyncClient(timeout=httpx.Timeout(timeout, connect=10.0)) as client:
        resp = await client.post(url, json=payload)
        resp.raise_for_status()
        data = resp.json()
    candidates = data.get("candidates", [])
    if not candidates:
        raise RuntimeError(f"Gemini returned no candidates: {data}")
    parts = candidates[0].get("content", {}).get("parts", [])
    if not parts:
        raise RuntimeError(f"Gemini returned no parts: {data}")
    return parts[0].get("text", "")


async def generate_content_and_script(topic: str) -> tuple[str, str]:
    """Gemini APIで記事本文と台本を生成（httpx直接呼び出し、タイムアウト付き）"""

    # 1. 記事本文
    article_prompt = f"""以下のテーマについて、ポッドキャスト配信用の記事本文を日本語で書いてください。

テーマ: {topic}

要件:
- 800〜1200文字程度の記事
- h2見出しを2-3個使用（## 記法）
- 事実に基づいた深い考察
- 具体的なデータや事例を含める
- HTMLタグは使わず、プレーンテキストで
"""

    body = await call_gemini(article_prompt)

    # 2. 台本
    script_prompt = PODCAST_SCRIPT_PROMPT + f"""

以下の記事をポッドキャスト台本に変換してください。
英語は絶対に使わないでください。すべて日本語で出力してください。

タイトル: {topic}

本文:
{body}"""

    script = await call_gemini(script_prompt)

    # イントロ・アウトロ追加
    intro = (
        f"山口: みなさん、こんにちは。DeepCastの時間です。今日は「{topic}」について話していきましょう。\n"
        f"田中: 楽しみですね！早速いきましょう。\n\n"
    )
    outro = (
        "\n\n山口: ということで、今日はこのあたりで。いかがでしたか？\n"
        "田中: すごく勉強になりました！リスナーのみなさんもぜひ考えてみてくださいね。\n"
        "山口: それでは、また次回のDeepCastでお会いしましょう。\n"
        "田中: ありがとうございました！"
    )

    full_script = intro + script + outro

    # クリーニング
    full_script = re.sub(r'\*\*(.+?)\*\*', r'\1', full_script)
    full_script = re.sub(r'\*(.+?)\*', r'\1', full_script)
    full_script = re.sub(r'`(.+?)`', r'\1', full_script)
    full_script = re.sub(r'https?://\S+', '', full_script)
    full_script = re.sub(r'#', '', full_script)
    full_script = re.sub(r'[-=]{3,}', '', full_script)
    full_script = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', full_script)
    full_script = re.sub(r'\n{3,}', '\n\n', full_script)

    return body, full_script


async def synthesize_edge_dialogue(script: str, title: str) -> Path:
    """Edge-TTSで対話音声を生成（山口と田中を別ボイスで）"""
    ts = int(time.time() * 1000)
    safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:30].strip()

    # 台本をパースして話者ごとに分割
    lines = script.strip().split('\n')
    segments = []
    current_speaker = None
    current_text = []

    for line in lines:
        line = line.strip()
        if not line:
            continue
        if line.startswith('山口:') or line.startswith('山口：'):
            if current_speaker and current_text:
                segments.append((current_speaker, ' '.join(current_text)))
            current_speaker = 'yamaguchi'
            text = re.sub(r'^山口[:：]\s*', '', line).strip()
            current_text = [text] if text else []
        elif line.startswith('田中:') or line.startswith('田中：'):
            if current_speaker and current_text:
                segments.append((current_speaker, ' '.join(current_text)))
            current_speaker = 'tanaka'
            text = re.sub(r'^田中[:：]\s*', '', line).strip()
            current_text = [text] if text else []
        else:
            if current_speaker:
                current_text.append(line)

    if current_speaker and current_text:
        segments.append((current_speaker, ' '.join(current_text)))

    if not segments:
        # パースできなかった場合、全体を一つのボイスで
        segments = [('yamaguchi', script)]

    # 各セグメントを個別にTTS
    part_files = []
    for i, (speaker, text) in enumerate(segments):
        if not text.strip():
            continue
        voice = VOICE_YAMAGUCHI if speaker == 'yamaguchi' else VOICE_TANAKA
        rate = "-10%" if speaker == 'yamaguchi' else "+0%"
        part_path = AUDIO_DIR / f"_part_{ts}_{i}.mp3"

        communicate = edge_tts.Communicate(text, voice, rate=rate)
        await communicate.save(str(part_path))
        if part_path.exists() and part_path.stat().st_size > 0:
            part_files.append(part_path)

    if not part_files:
        raise RuntimeError("音声パーツが生成されませんでした")

    # ffmpegで結合
    final_path = AUDIO_DIR / f"{safe_title}_{ts}.mp3"

    if len(part_files) == 1:
        part_files[0].rename(final_path)
    else:
        # concat listファイル作成（絶対パス、forward slash使用）
        list_path = AUDIO_DIR / f"_concat_{ts}.txt"
        with open(list_path, 'w', encoding='utf-8') as f:
            for pf in part_files:
                abs_path = str(pf.resolve()).replace('\\', '/')
                f.write(f"file '{abs_path}'\n")

        try:
            result = subprocess.run(
                ["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(list_path.resolve()),
                 "-c:a", "libmp3lame", "-b:a", "192k",
                 str(final_path.resolve())],
                capture_output=True,
            )
            if result.returncode != 0:
                err = result.stderr.decode('utf-8', errors='replace')[:300]
                print(f"  -> ffmpeg失敗: {err}")
                import shutil
                # 全パーツを順に連結（バイナリ結合）
                with open(str(final_path), 'wb') as out:
                    for pf in part_files:
                        out.write(pf.read_bytes())
        finally:
            list_path.unlink(missing_ok=True)

    # パーツファイル削除
    for pf in part_files:
        pf.unlink(missing_ok=True)

    return final_path


def get_next_episode_number() -> int:
    if not EPISODES_JSON.exists():
        return 1
    with open(EPISODES_JSON, "r", encoding="utf-8") as f:
        episodes = json.load(f)
    if not episodes:
        return 1
    max_id = max(ep["id"] for ep in episodes)
    return max_id + 1


# テンプレートHTML（起動時に読み込む）
_TEMPLATE_HTML = ""


def create_episode_html(ep_num: int, title: str, body: str, description: str) -> Path:
    template = _TEMPLATE_HTML
    ep_str = f"ep{ep_num:03d}"
    today = datetime.now().strftime("%Y-%m-%d")

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

    html = template
    html = re.sub(r'<title>.*?</title>', f'<title>#{ep_num} {title}｜DeepCast AI</title>', html)
    html = re.sub(r'<meta name="description" content=".*?"', f'<meta name="description" content="{description[:160]}"', html)
    html = re.sub(r'<link rel="canonical" href=".*?"', f'<link rel="canonical" href="https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'<meta property="og:title" content=".*?"', f'<meta property="og:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    html = re.sub(r'<meta property="og:description" content=".*?"', f'<meta property="og:description" content="{description[:160]}"', html)
    html = re.sub(r'<meta property="og:url" content=".*?"', f'<meta property="og:url" content="https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'<meta name="twitter:title" content=".*?"', f'<meta name="twitter:title" content="#{ep_num} {title}｜DeepCast AI"', html)
    html = re.sub(r'<meta name="twitter:description" content=".*?"', f'<meta name="twitter:description" content="{description[:160]}"', html)
    html = re.sub(
        r'(<div class="article-body">).*?(</div>\s*</article>)',
        rf'\1\n{article_html}\n\2',
        html, flags=re.DOTALL,
    )
    html = re.sub(r'"name":"#\d+ .*?"', f'"name":"#{ep_num} {title}"', html)
    html = re.sub(r'"episodeNumber":\s*\d+', f'"episodeNumber": {ep_num}', html)
    html = re.sub(r'"datePublished":\s*"[^"]*"', f'"datePublished": "{today}"', html)
    html = re.sub(r'"name":\s*"[^"]*"(,\s*"url":\s*"https://deepcast-ai\.com/episodes/)', f'"name": "#{ep_num} {title}"\\1', html)
    html = re.sub(r'"url":\s*"https://deepcast-ai\.com/episodes/ep\d+\.html"', f'"url": "https://deepcast-ai.com/episodes/{ep_str}.html"', html)
    html = re.sub(r'"contentUrl":\s*"[^"]*"', f'"contentUrl": "https://audio.deepcast-ai.com/{ep_str}.mp3"', html)

    out_path = EPISODES_DIR / f"{ep_str}.html"
    out_path.write_text(html, encoding="utf-8")
    return out_path


def update_episodes_json(ep_num: int, title: str, description: str, duration: str, category: str, tags: list[str], tier: str = "free"):
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
    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY_ID,
        aws_secret_access_key=R2_SECRET_ACCESS_KEY,
        region_name="auto",
    )
    local_path = str(EPISODES_DIR / f"{ep_str}.mp3")
    s3.upload_file(local_path, R2_BUCKET, f"{ep_str}.mp3", ExtraArgs={"ContentType": "audio/mpeg"})


async def process_topic(index: int, topic: str, total: int):
    """1トピックを処理"""
    import shutil
    ep_num = get_next_episode_number()
    ep_str = f"ep{ep_num:03d}"

    # Free/Pro: 最新3つがFree
    tier = "free" if ep_num > (total - 3) else "pro"

    print(f"\n{'='*60}")
    print(f"[{ep_str}] ({index+1}/{total}) {topic} [{tier.upper()}]")
    print(f"{'='*60}")

    # 1. コンテンツ＆台本生成
    print("  [1/5] コンテンツ＆台本生成中...")
    body, script = await generate_content_and_script(topic)
    print(f"  -> 記事: {len(body)}文字, 台本: {len(script)}文字")

    description = body[:200].replace("\n", " ").strip()
    if len(description) > 150:
        description = description[:150] + "..."

    # 2. Edge-TTS音声生成
    print("  [2/5] Edge-TTS音声生成中...")
    audio_path = await synthesize_edge_dialogue(script, topic)
    dest = EPISODES_DIR / f"{ep_str}.mp3"
    shutil.copy2(str(audio_path), str(dest))
    audio_path.unlink(missing_ok=True)

    file_size = dest.stat().st_size
    # Edge-TTS MP3は約128kbps = 16KB/s, ffmpeg後は192kbps = 24KB/s
    duration_sec = file_size / 16000  # 128kbps推定
    minutes = int(duration_sec // 60)
    seconds = int(duration_sec % 60)
    duration_str = f"{minutes}:{seconds:02d}"
    print(f"  -> {dest.name} ({duration_str})")

    # 3. HTML生成
    print("  [3/5] HTML生成中...")
    create_episode_html(ep_num, topic, body, description)

    # 4. episodes.json更新
    print("  [4/5] episodes.json更新中...")
    category = "tech"
    tags = [w.strip() for w in topic.replace("—", " ").replace("―", " ").split() if len(w.strip()) > 1][:4]
    update_episodes_json(ep_num, topic, description, duration_str, category, tags, tier)

    # 5. R2アップロード
    print("  [5/5] R2アップロード中...")
    try:
        upload_to_r2(ep_str)
        print(f"  -> R2アップロード完了")
    except Exception as e:
        print(f"  -> R2アップロード失敗（後で再アップ可能）: {e}")

    print(f"  [DONE] {ep_str}: {topic} ({duration_str}) [{tier.upper()}]")
    return ep_num


async def main():
    global _TEMPLATE_HTML

    # テンプレート読み込み
    template_path = EPISODES_DIR / "ep001.html"
    if template_path.exists():
        _TEMPLATE_HTML = template_path.read_text(encoding="utf-8")
        print(f"テンプレート読み込み完了: {len(_TEMPLATE_HTML)}文字")
    else:
        print("ERROR: ep001.htmlテンプレートが見つかりません")
        return

    # episodes.jsonリセット
    print("episodes.jsonをリセット...")
    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump([], f)

    # 既存ファイル削除
    print("既存エピソードファイルを削除...")
    for i in range(1, 20):
        ep_str = f"ep{i:03d}"
        for ext in [".mp3"]:  # HTMLはテンプレート以外を削除
            fp = EPISODES_DIR / f"{ep_str}{ext}"
            if fp.exists():
                fp.unlink()
                print(f"  削除: {fp.name}")
    for i in range(2, 20):  # ep001.htmlはテンプレートなので残す
        fp = EPISODES_DIR / f"ep{i:03d}.html"
        if fp.exists():
            fp.unlink()
            print(f"  削除: {fp.name}")

    total = len(TOPICS)
    print(f"\n生成開始: {total}本")
    generated = 0

    for i, topic in enumerate(TOPICS):
        try:
            await process_topic(i, topic, total)
            generated += 1
            await asyncio.sleep(3)
        except Exception as e:
            print(f"  [ERROR] {topic}: {e}")
            traceback.print_exc()
            await asyncio.sleep(3)
            continue

    print(f"\n{'='*60}")
    print(f"完了: {generated}/{total}本生成")

    with open(EPISODES_JSON, "r", encoding="utf-8") as f:
        episodes = json.load(f)
    print(f"\nepisodes.json: {len(episodes)}件")
    for ep in episodes:
        print(f"  #{ep['id']} [{ep.get('tier', 'free')}] {ep['title']} ({ep['duration']})")


if __name__ == "__main__":
    asyncio.run(main())

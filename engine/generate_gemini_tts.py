"""Gemini TTS音声生成 → R2アップロード → episodes.json・HTML更新.

全10エピソードの音声をGemini TTSで生成し、R2にアップロード。
Free/Pro tier分類を正しく設定。
"""
import asyncio
import io
import json
import os
import re
import struct
import subprocess
import sys
import time
from pathlib import Path

if hasattr(sys.stdout, 'buffer'):
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace', line_buffering=True)
if hasattr(sys.stderr, 'buffer'):
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace', line_buffering=True)

import boto3
from dotenv import load_dotenv
from google import genai

load_dotenv()

SITE_DIR = Path("G:/マイドライブ/株式会社　礼/運用中/8_ディープキャスト")
EPISODES_DIR = SITE_DIR / "episodes"
EPISODES_JSON = EPISODES_DIR / "episodes.json"

GEMINI_API_KEY = os.environ.get("GEMINI_API_KEY", "")
R2_ENDPOINT = os.environ.get("R2_ENDPOINT", "")
R2_ACCESS_KEY = os.environ.get("R2_ACCESS_KEY_ID", "")
R2_SECRET_KEY = os.environ.get("R2_SECRET_ACCESS_KEY", "")
R2_BUCKET = "deepcast-audio"
R2_PUBLIC_URL = "https://audio.deepcast-ai.com"


def gemini_tts(script: str, output_wav: Path, max_retries: int = 5) -> bool:
    """Gemini TTSで台本を音声合成（WAVで保存）"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    tts_prompt = (
        "以下のポッドキャスト台本を自然に読み上げてください。\n"
        "【重要】全体的にゆっくりめのペースで話してください。急がず、一文一文丁寧に。\n"
        "メインパーソナリティは神宮寺です。落ち着いた知的な男性の声で読んでください。\n"
        "葵が登場する場合は、明るく高めの声で演じ分けてください。\n"
        "「神宮寺:」「葵:」のラベルは読み上げないでください。\n"
        "会話の間を多めに取り、リラックスして聴けるテンポで読んでください。\n\n"
        + script
    )

    for attempt in range(max_retries):
        try:
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=tts_prompt,
                config=genai.types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=genai.types.SpeechConfig(
                        voice_config=genai.types.VoiceConfig(
                            prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                                voice_name="Enceladus",
                            )
                        )
                    ),
                ),
            )
            if (not response.candidates or not response.candidates[0].content
                    or not response.candidates[0].content.parts):
                raise RuntimeError("Empty response from Gemini TTS")

            audio_data = response.candidates[0].content.parts[0].inline_data.data
            data_size = len(audio_data)
            header = struct.pack(
                '<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE',
                b'fmt ', 16, 1, 1, 24000, 24000 * 2, 2, 16,
                b'data', data_size,
            )
            output_wav.write_bytes(header + audio_data)
            return True

        except Exception as e:
            wait = (attempt + 1) * 15
            print(f"    [TTS リトライ {attempt+1}/{max_retries}] {e}")
            print(f"    -> {wait}秒待機...")
            time.sleep(wait)

    return False


def wav_to_mp3(wav_path: Path, mp3_path: Path) -> bool:
    """WAV→MP3変換（ffmpeg使用）"""
    try:
        result = subprocess.run(
            ["ffmpeg", "-y", "-i", str(wav_path),
             "-af", "loudnorm=I=-16:TP=-3:LRA=13",
             "-ar", "44100", "-b:a", "128k",
             str(mp3_path)],
            capture_output=True, timeout=120,
        )
        return result.returncode == 0 and mp3_path.exists()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False


def upload_to_r2(local_path: Path, key: str) -> str:
    """R2にアップロード"""
    s3 = boto3.client(
        "s3",
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        region_name="auto",
    )
    s3.upload_file(str(local_path), R2_BUCKET, key, ExtraArgs={"ContentType": "audio/mpeg"})
    return f"{R2_PUBLIC_URL}/{key}"


def get_duration(file_path: Path) -> str:
    """MP3の再生時間推定"""
    size = file_path.stat().st_size
    seconds = size / 16000  # 128kbps
    return f"{int(seconds//60)}:{int(seconds%60):02d}"


async def generate_article(title: str) -> str:
    """Gemini APIで記事本文を生成"""
    client = genai.Client(api_key=GEMINI_API_KEY)
    prompt = f"""以下のテーマについて、ポッドキャスト配信用の記事本文を日本語で書いてください。

テーマ: {title}

要件:
- 800〜1200文字の記事
- h2見出しを2-3個使用（マークダウン##記法）
- 事実に基づいた深い考察
- 具体的なデータや事例
- 結論で新しい視点を提示
- HTMLタグは使わない
"""
    def _gen():
        for attempt in range(3):
            try:
                resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                return resp.text
            except Exception as e:
                print(f"    [記事生成リトライ {attempt+1}/3] {e}")
                time.sleep(10 * (attempt + 1))
        return title
    return await asyncio.to_thread(_gen)


def create_episode_html(ep_num: int, title: str, body: str, audio_url: str, tier: str) -> Path:
    """エピソードHTMLを新規作成"""
    ep_str = f"ep{ep_num:03d}"
    today = time.strftime("%Y-%m-%d")
    desc = body[:160].replace("\n", " ").replace('"', "'")

    sections = body.strip().split("\n\n")
    article_html = ""
    for s in sections:
        s = s.strip()
        if not s: continue
        if s.startswith("## "):
            article_html += f'        <h2>{s[3:].strip()}</h2>\n'
        else:
            article_html += f'        <p>{s}</p>\n'

    player = f'''<audio controls preload="metadata" style="width:100%;">
        <source src="{audio_url}" type="audio/mpeg">
      </audio>''' if audio_url else '<p style="color:#8e8e93;font-size:0.9rem;padding:1rem;background:#f5f5f7;border-radius:8px;text-align:center;">音声は準備中です。</p>'

    html = f'''<!DOCTYPE html>
<html lang="ja">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>#{ep_num} {title}｜DeepCast AI</title>
<meta name="description" content="{desc}">
<link rel="canonical" href="https://deepcast-ai.com/episodes/{ep_str}.html">
<link rel="stylesheet" href="/assets/css/style.css">
<link rel="stylesheet" href="/css/style.css">
</head>
<body>
<header class="site-header">
  <nav class="nav">
    <a href="/" class="nav__logo">DeepCast AI</a>
    <div class="nav__links">
      <a href="/all-episodes.html" class="nav__link">全エピソード</a>
      <a href="/pages/pricing.html" class="nav__link">料金</a>
    </div>
  </nav>
</header>
<main class="episode-page">
  <article class="episode-detail">
    <div class="episode-detail__header">
      <span class="episode-detail__number">#{ep_num}</span>
      <h1 class="episode-detail__title">{title}</h1>
      <time class="episode-detail__date">{today}</time>
    </div>
    <div class="episode-detail__player">
      {player}
    </div>
    <div class="article-body">
{article_html}
    </div>
  </article>
</main>
<footer class="site-footer">
  <p>&copy; 2026 DeepCast AI — 濱田礼</p>
  <nav>
    <a href="/pages/terms.html">利用規約</a>
    <a href="/pages/privacy.html">プライバシーポリシー</a>
    <a href="/pages/tokushoho.html">特商法</a>
    <a href="/pages/contact.html">お問い合わせ</a>
  </nav>
</footer>
<script src="/assets/js/auth.js?v=20260327"></script>
</body>
</html>'''
    out = EPISODES_DIR / f"{ep_str}.html"
    out.write_text(html, encoding="utf-8")
    return out


async def generate_script_gemini(title: str, body: str) -> str:
    """Gemini APIで台本生成"""
    client = genai.Client(api_key=GEMINI_API_KEY)

    prompt = f"""以下の記事をポッドキャスト台本（2分30秒、約600〜800文字）に変換してください。

パーソナリティ: 神宮寺（メインMC）
- テーマに応じて、神宮寺の1人語りか、葵（アシスタント）との対話形式を選んでください
- 対話形式の場合は「神宮寺:」「葵:」で発言を区別
- 1人語りの場合は「神宮寺:」のみ
- 落ち着いた知的なトーンで、リスナーに語りかけるように
- 専門用語は噛み砕いて説明

タイトル: {title}
本文: {body[:2000]}
"""

    def _gen():
        for attempt in range(3):
            try:
                resp = client.models.generate_content(model="gemini-2.5-flash", contents=prompt)
                return resp.text
            except Exception as e:
                print(f"    [台本リトライ {attempt+1}/3] {e}")
                time.sleep(10 * (attempt + 1))
        return None

    return await asyncio.to_thread(_gen)


async def process_episode(ep_num: int, title: str, body: str, tier: str) -> dict:
    """1エピソードを処理: 台本生成→TTS→R2"""
    ep_str = f"ep{ep_num:03d}"

    print(f"\n{'='*60}")
    print(f"[{ep_str}] {title} [{tier.upper()}]")
    print(f"{'='*60}")

    # 1. 台本生成
    print(f"  [1/4] 台本生成中...")
    script = await generate_script_gemini(title, body)
    if not script:
        print(f"  [ERROR] 台本生成失敗")
        return None

    # イントロ・アウトロ（台本に含まれていなければ追加）
    if not script.strip().startswith("神宮寺"):
        script = f"神宮寺: みなさんこんにちは。DeepCastの神宮寺です。今日は「{title}」について話していきます。\n\n" + script
    if "また次回" not in script and "ありがとう" not in script[-100:]:
        script += "\n\n神宮寺: それでは、また次回のDeepCastでお会いしましょう。"
    intro = ""
    outro = ""
    full_script = intro + script + outro
    print(f"  -> 台本OK ({len(full_script)}文字)")

    # 2. Gemini TTS
    print(f"  [2/4] Gemini TTS音声生成中...")
    wav_path = EPISODES_DIR / f"_tmp_{ep_str}.wav"
    mp3_path = EPISODES_DIR / f"{ep_str}.mp3"

    # チャンク分割（1500文字以内に）
    chunks = []
    current = ""
    for line in full_script.split("\n"):
        if len(current) + len(line) > 1400 and current:
            chunks.append(current)
            current = line + "\n"
        else:
            current += line + "\n"
    if current.strip():
        chunks.append(current)

    print(f"  -> {len(chunks)}チャンクに分割")

    all_wav_data = b""
    for ci, chunk in enumerate(chunks):
        print(f"    チャンク {ci+1}/{len(chunks)} ({len(chunk)}文字)...")
        chunk_wav = EPISODES_DIR / f"_tmp_{ep_str}_c{ci}.wav"
        success = await asyncio.to_thread(gemini_tts, chunk, chunk_wav)
        if success and chunk_wav.exists():
            wav_bytes = chunk_wav.read_bytes()
            # WAVヘッダー(44bytes)をスキップしてデータ部分のみ取得
            if len(wav_bytes) > 44:
                all_wav_data += wav_bytes[44:]
            chunk_wav.unlink(missing_ok=True)
            print(f"    -> OK ({len(wav_bytes)} bytes)")
        else:
            print(f"    -> FAILED")
            chunk_wav.unlink(missing_ok=True)

    if not all_wav_data:
        print(f"  [ERROR] 音声生成失敗")
        return None

    # 結合WAV作成
    header = struct.pack(
        '<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(all_wav_data), b'WAVE',
        b'fmt ', 16, 1, 1, 24000, 24000 * 2, 2, 16,
        b'data', len(all_wav_data),
    )
    wav_path.write_bytes(header + all_wav_data)

    # WAV→MP3変換
    converted = await asyncio.to_thread(wav_to_mp3, wav_path, mp3_path)
    wav_path.unlink(missing_ok=True)

    if not converted:
        print(f"  [WARN] ffmpeg変換失敗、WAVをそのまま使用")
        # WAVをmp3として保存（ブラウザは再生可能）
        wav_path2 = EPISODES_DIR / f"_tmp2_{ep_str}.wav"
        if wav_path2.exists():
            import shutil
            shutil.copy2(str(wav_path2), str(mp3_path))

    if not mp3_path.exists() or mp3_path.stat().st_size < 1000:
        print(f"  [ERROR] MP3生成失敗")
        return None

    duration = get_duration(mp3_path)
    size_mb = mp3_path.stat().st_size / (1024 * 1024)
    print(f"  -> {ep_str}.mp3 ({duration}, {size_mb:.1f}MB)")

    # 3. R2アップロード
    print(f"  [3/4] R2アップロード中...")
    try:
        audio_url = await asyncio.to_thread(upload_to_r2, mp3_path, f"{ep_str}.mp3")
        print(f"  -> {audio_url}")
    except Exception as e:
        print(f"  [ERROR] R2: {e}")
        audio_url = ""

    # 4. HTML作成
    print(f"  [4/4] HTML作成中...")
    create_episode_html(ep_num, title, body, audio_url, tier)

    print(f"  [DONE] {ep_str}: {title} ({duration})")

    return {
        "audio": audio_url,
        "duration": duration,
    }


async def main():
    # まずepisodes.jsonを正しい10本に整理
    # ep001-007: Pro, ep008-010: Free
    correct_episodes = [
        {"id": 1, "title": "AIが書いた論文を見抜けない — 学術界を揺るがす生成AIの衝撃", "tier": "pro"},
        {"id": 2, "title": "量子コンピュータが暗号を破る日 — いつ来るのか、どう備えるか", "tier": "pro"},
        {"id": 3, "title": "脳とAIの境界線 — ニューラリンクが開く人間拡張の未来", "tier": "pro"},
        {"id": 4, "title": "SNSアルゴリズムが選挙を動かす — デジタル民主主義の光と影", "tier": "pro"},
        {"id": 5, "title": "なぜGAFAMは宇宙開発に巨額投資するのか — テック企業の宇宙戦略", "tier": "pro"},
        {"id": 6, "title": "自動運転車の「トロッコ問題」 — AIに命の選択を任せられるか", "tier": "pro"},
        {"id": 7, "title": "ディープフェイクが変える情報戦 — 真実を見極める時代の終わり", "tier": "pro"},
        {"id": 8, "title": "電子ゴミが地球を覆う — テクノロジーの裏にある環境コスト", "tier": "free"},
        {"id": 9, "title": "AIが医師を超える日 — 診断精度99%の衝撃と残る課題", "tier": "free"},
        {"id": 10, "title": "プログラミング不要の時代 — ノーコード革命は本物か幻か", "tier": "free"},
    ]

    # 不要なエピソード(ep011-013)のファイルを削除
    for i in range(11, 20):
        for ext in [".html", ".mp3"]:
            fp = EPISODES_DIR / f"ep{i:03d}{ext}"
            if fp.exists():
                fp.unlink()
                print(f"削除: {fp.name}")

    # 各エピソードのHTMLから本文を取得
    today = time.strftime("%Y.%m.%d")
    results = []

    for ep_info in correct_episodes:
        ep_num = ep_info["id"]
        ep_str = f"ep{ep_num:03d}"
        title = ep_info["title"]
        tier = ep_info["tier"]

        # Gemini APIで記事本文を生成
        body = await generate_article(title)

        result = await process_episode(ep_num, title, body, tier)

        description = body[:150].replace("\n", " ").strip()
        if len(description) > 140:
            description = description[:140] + "..."

        tags = [w.strip() for w in title.replace("—", " ").split() if len(w.strip()) > 1][:4]

        ep_data = {
            "id": ep_num,
            "title": title,
            "description": description,
            "date": today,
            "category": "tech",
            "tags": tags,
            "duration": result["duration"] if result else "2:30",
            "audio": result["audio"] if result else "",
            "article": f"episodes/{ep_str}.html",
            "language": "ja",
            "tier": tier,
        }
        results.append(ep_data)

        # API冷却
        await asyncio.sleep(5)

    # 新しい順にソート
    results.sort(key=lambda e: e["id"], reverse=True)

    with open(EPISODES_JSON, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)

    print(f"\n{'='*60}")
    print(f"完了!")
    with_audio = sum(1 for e in results if e["audio"])
    free_count = sum(1 for e in results if e["tier"] == "free")
    pro_count = sum(1 for e in results if e["tier"] == "pro")
    print(f"音声あり: {with_audio}/{len(results)}本")
    print(f"Free: {free_count}本 / Pro: {pro_count}本")


if __name__ == "__main__":
    asyncio.run(main())

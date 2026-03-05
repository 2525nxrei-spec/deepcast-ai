"""DeepCast AI - 20 episode auto-generator (2-step: script + TTS)"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import json, struct, os, time
from google import genai

API_KEY = "AIzaSyAIiFAZZFzZFshD3AWicsowCmbt_JO8Wl0"
OUTPUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "episodes")
SCRIPTS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "scripts")
os.makedirs(SCRIPTS_DIR, exist_ok=True)

client = genai.Client(api_key=API_KEY)

with open(os.path.join(OUTPUT_DIR, "episodes.json"), "r", encoding="utf-8") as f:
    episodes = json.load(f)
episodes.sort(key=lambda x: x["id"])


def pcm_to_wav(pcm_data, sample_rate=24000):
    data_size = len(pcm_data)
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + data_size, b'WAVE',
        b'fmt ', 16, 1, 1, sample_rate, sample_rate * 2, 2, 16,
        b'data', data_size)
    return header + pcm_data


def generate_script(title, desc):
    """Step 1: Gemini Flash で台本生成"""
    prompt = f"""あなたはポッドキャスト「DeepCast AI」の台本作家です。
以下のテーマで、約3分間のポッドキャスト台本を書いてください。

テーマ: {title}
概要: {desc}

ルール:
- 冒頭: 「DeepCast AI。今日のテーマは、{title}」で始める
- 本文: わかりやすくカジュアルに。具体例を交える。「ですます」調。
- 締め: 「DeepCast AI、また次回お会いしましょう」で終わる
- 一人語り形式で書く（対話ではない）
- 台本のテキストだけを出力（ト書きや注釈は不要）
- 800〜1200文字程度"""

    response = client.models.generate_content(
        model="gemini-2.0-flash",
        contents=prompt,
    )
    return response.text


def generate_audio(script_text, filepath):
    """Step 2: TTS で読み上げ"""
    # TTSモデルには「読み上げてください」と明確に指示
    tts_prompt = f"以下のテキストを、落ち着いた声でそのまま読み上げてください。\n\n{script_text}"

    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=tts_prompt,
        config=genai.types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=genai.types.SpeechConfig(
                voice_config=genai.types.VoiceConfig(
                    prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                        voice_name="Zephyr"
                    )
                )
            ),
        ),
    )

    audio_data = response.candidates[0].content.parts[0].inline_data.data
    wav_data = pcm_to_wav(audio_data)
    with open(filepath, "wb") as f:
        f.write(wav_data)
    return os.path.getsize(filepath)


for ep in episodes:
    ep_id = ep["id"]
    wav_path = os.path.join(OUTPUT_DIR, f"ep{ep_id:03d}.wav")
    script_path = os.path.join(SCRIPTS_DIR, f"ep{ep_id:03d}.txt")

    if os.path.exists(wav_path):
        print(f"[SKIP] ep{ep_id:03d}.wav already exists")
        continue

    title = ep["title"]
    desc = ep["description"]
    print(f"[{ep_id}/20] {title}")

    try:
        # Step 1: 台本生成
        if os.path.exists(script_path):
            with open(script_path, "r", encoding="utf-8") as f:
                script = f.read()
            print(f"  台本: キャッシュから読み込み ({len(script)}文字)")
        else:
            print(f"  台本生成中...")
            script = generate_script(title, desc)
            with open(script_path, "w", encoding="utf-8") as f:
                f.write(script)
            print(f"  台本: {len(script)}文字")
            time.sleep(2)

        # Step 2: TTS
        print(f"  音声生成中...")
        size = generate_audio(script, wav_path)
        size_mb = size / (1024 * 1024)
        print(f"  完了! ep{ep_id:03d}.wav ({size_mb:.1f} MB)")

        # レート制限対策: TTS free tier = 10 req/min
        print(f"  待機中 (レート制限対策)...")
        time.sleep(15)

    except Exception as e:
        print(f"  ERROR: {e}")
        print(f"  60秒待機してリトライ...")
        time.sleep(60)

print("\n=== 完了! ===")
generated = [f for f in os.listdir(OUTPUT_DIR) if f.endswith('.wav')]
print(f"生成済み: {len(generated)}/20")

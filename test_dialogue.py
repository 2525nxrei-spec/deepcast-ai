"""Test: dialogue-style podcast with natural voices"""
import sys, io, struct, os
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

from google import genai

API_KEY = "AIzaSyAIiFAZZFzZFshD3AWicsowCmbt_JO8Wl0"
client = genai.Client(api_key=API_KEY)

# Step 1: Generate dialogue script
print("Step 1: Generating dialogue script...")
script_resp = client.models.generate_content(
    model="gemini-2.0-flash",
    contents="""あなたはポッドキャスト「DeepCast AI」の台本作家です。
2人のホスト（ホストA：落ち着いた男性、ホストB：好奇心旺盛な女性）の対話形式で台本を書いてください。

テーマ: なぜ"やる気"は待っても来ないのか — 行動が先、感情は後の法則
概要: 作業興奮、側坐核の起動条件、5秒ルール。やる気の正体と、今すぐ動ける脳科学的ハック。

ルール:
- 冒頭: A「DeepCast AI。今日のテーマは...」で始める
- 2人が自然に会話しながらテーマを掘り下げる
- 具体例や身近なエピソードを交える
- 「へー」「なるほど」「それ分かる」など相槌を自然に入れる
- 締め: A「DeepCast AI、また次回お会いしましょう」B「バイバーイ！」
- 台本テキストだけ出力。話者名は「A:」「B:」で示す
- 約800文字"""
)
script = script_resp.text
print(f"Script: {len(script)} chars")
print(script[:300] + "...")

# Step 2: TTS with multi-speaker
print("\nStep 2: Generating audio...")
tts_prompt = f"以下の対話台本を、2人の声で自然に読み上げてください。Aは落ち着いた声、Bは明るい声でお願いします。\n\n{script}"

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents=tts_prompt,
        config=genai.types.GenerateContentConfig(
            response_modalities=["AUDIO"],
            speech_config=genai.types.SpeechConfig(
                multi_speaker_voice_config=genai.types.MultiSpeakerVoiceConfig(
                    speaker_voice_configs=[
                        genai.types.SpeakerVoiceConfig(
                            speaker="A",
                            voice_config=genai.types.VoiceConfig(
                                prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                                    voice_name="Kore"
                                )
                            ),
                        ),
                        genai.types.SpeakerVoiceConfig(
                            speaker="B",
                            voice_config=genai.types.VoiceConfig(
                                prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                                    voice_name="Leda"
                                )
                            ),
                        ),
                    ]
                )
            ),
        ),
    )

    data = response.candidates[0].content.parts[0].inline_data.data
    sr = 24000
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(data), b'WAVE',
        b'fmt ', 16, 1, 1, sr, sr * 2, 2, 16,
        b'data', len(data))

    outpath = "G:/マイドライブ/deep cast/episodes/test_dialogue.wav"
    with open(outpath, "wb") as f:
        f.write(header + data)

    size_mb = os.path.getsize(outpath) / (1024 * 1024)
    print(f"Success! Saved test_dialogue.wav ({size_mb:.1f} MB)")

except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

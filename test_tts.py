"""Quick test: generate 1 short audio clip"""
import sys, io
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

import struct
from google import genai

client = genai.Client(api_key="AIzaSyAIiFAZZFzZFshD3AWicsowCmbt_JO8Wl0")

print("Sending request to Gemini TTS...")

try:
    response = client.models.generate_content(
        model="gemini-2.5-flash-preview-tts",
        contents="DeepCast AI, hello world. This is a test.",
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

    data = response.candidates[0].content.parts[0].inline_data.data
    mime = response.candidates[0].content.parts[0].inline_data.mime_type
    print(f"Success! Got {len(data)} bytes, mime: {mime}")

    # Save as WAV
    sr = 24000
    header = struct.pack('<4sI4s4sIHHIIHH4sI',
        b'RIFF', 36 + len(data), b'WAVE',
        b'fmt ', 16, 1, 1, sr, sr * 2, 2, 16,
        b'data', len(data))

    with open("G:/マイドライブ/deep cast/episodes/test.wav", "wb") as f:
        f.write(header + data)
    print("Saved test.wav!")

except Exception as e:
    print(f"Error: {type(e).__name__}: {e}")

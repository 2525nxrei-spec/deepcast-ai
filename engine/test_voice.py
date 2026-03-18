import asyncio
import edge_tts
import sqlite3
import os

async def main():
    os.makedirs("data/audio", exist_ok=True)
    conn = sqlite3.connect("data/deepcast.db")
    row = conn.execute("SELECT title, body FROM contents WHERE id=2").fetchone()
    conn.close()

    text = f"{row[0]}. {row[1][:500]}"
    print(f"Text length: {len(text)} chars")
    print(f"Text preview: {text[:100]}...")

    communicate = edge_tts.Communicate(text, "en-US-GuyNeural")
    await communicate.save("data/audio/test_en.mp3")

    size = os.path.getsize("data/audio/test_en.mp3")
    print(f"Audio generated: data/audio/test_en.mp3 ({size} bytes)")

asyncio.run(main())

"""全公開エピソードの音声を再生成するスクリプト"""
import asyncio
import sqlite3
import shutil
from pathlib import Path

# プロジェクトのモジュールをインポート
from config.settings import settings
from core.voice_engine import VoiceEngine


# DB ID → エピソードファイル名の対応
EPISODE_MAP = {
    11: "ep002",  # サステナブルファイナンス
    13: "ep003",  # AI倫理の現在
    14: "ep004",  # 時代の変化
}

SITE_DIR = Path(settings.SITE_ROOT)
EPISODES_DIR = SITE_DIR / "episodes"


async def regenerate_all():
    engine = VoiceEngine()

    conn = sqlite3.connect("data/deepcast.db")
    conn.row_factory = sqlite3.Row

    for db_id, ep_name in EPISODE_MAP.items():
        row = conn.execute(
            "SELECT title, body FROM contents WHERE id = ?", (db_id,)
        ).fetchone()

        if not row:
            print(f"[SKIP] DB ID {db_id} not found")
            continue

        title = row["title"]
        body = row["body"]
        print(f"\n{'='*60}")
        print(f"[START] {ep_name}: {title}")
        print(f"  body: {len(body)} chars")

        try:
            audio_path = await engine.synthesize_podcast(
                title=title,
                body=body,
                language="ja",
            )
            print(f"  generated: {audio_path}")

            # episodes/ フォルダにコピー
            dest = EPISODES_DIR / f"{ep_name}.mp3"
            shutil.copy2(str(audio_path), str(dest))
            print(f"  copied to: {dest}")
            print(f"[DONE] {ep_name}")

        except Exception as e:
            print(f"[ERROR] {ep_name}: {e}")
            import traceback
            traceback.print_exc()

    conn.close()
    print(f"\n{'='*60}")
    print("全エピソード再生成完了")


if __name__ == "__main__":
    asyncio.run(regenerate_all())

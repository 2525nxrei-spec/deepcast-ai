"""Standalone test: update content_id 2 to published and run Publisher."""

import asyncio
import sys
import io

# Force UTF-8 output on Windows
sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding="utf-8", errors="replace")
sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding="utf-8", errors="replace")

sys.path.insert(0, ".")

from config.settings import settings
from core.database import DatabaseManager
from manager.publisher import Publisher


async def main():
    db = DatabaseManager()
    await db.init_db()

    # Show current state
    content = await db.get_content(2)
    print(f"[BEFORE] content_id=2  status={content['status']}  title={content['title']}")

    # Update status to published (so publisher treats it as publishable)
    await db.update_content_status(2, "published")
    content = await db.get_content(2)
    print(f"[AFTER]  content_id=2  status={content['status']}")

    # Run publisher
    publisher = Publisher(db=db)
    print(f"\nSITE_ROOT = {settings.SITE_ROOT}")
    print(f"Next episode number will be: {await publisher.get_next_episode_number()}")

    results = await publisher.publish_episode(2)

    print("\n--- Publish Results ---")
    for r in results:
        status = "OK" if r.success else "FAIL"
        detail = r.file_path or r.error
        print(f"  {r.target.value}: {status} - {detail}")

    # Validate
    ep_num = await publisher.get_next_episode_number() - 1
    print(f"\n--- Validation (ep{ep_num:03d}) ---")
    issues = await publisher.validate_publish(ep_num)
    if issues:
        for issue in issues:
            print(f"  ISSUE: {issue}")
    else:
        print("  All validations passed!")

    await db.close()


if __name__ == "__main__":
    asyncio.run(main())

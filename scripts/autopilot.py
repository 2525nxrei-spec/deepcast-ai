"""DeepCast AI — 統合Autopilotスクリプト.

Windowsタスクスケジューラから呼び出すことを想定した、
エピソード自動生成・公開の統合エントリーポイント。

フロー:
  1. pipeline  → トレンド分析 → トピック選定 → 台本生成 → 品質評価
  2. voice     → Gemini TTS 音声生成（175-185秒バリデーション、最大3回リトライ）
  3. publish   → HTML/JSON/RSS/sitemap更新
  4. R2        → wrangler CLIでR2にmp3アップロード
  5. git push  → ブランチ作成 → push → PR自動作成

Usage:
    python scripts/autopilot.py                    # 日本語1エピソード
    python scripts/autopilot.py --both             # 日英両方
    python scripts/autopilot.py --count 2          # 2エピソード
    python scripts/autopilot.py --dry-run          # テスト実行
    python scripts/autopilot.py --lang en          # 英語のみ

タスクスケジューラ登録例（管理者PowerShell）:
    schtasks /create /tn "DeepCast_Autopilot" ^
        /tr "python \"G:\\マイドライブ\\株式会社　礼\\運用中\\8_ディープキャスト\\scripts\\autopilot.py\"" ^
        /sc daily /st 08:00 /f
"""

from __future__ import annotations

import argparse
import asyncio
import io
import logging
import os
import sys
from datetime import datetime, timezone, timedelta
from pathlib import Path

# engine/ をPythonパスに追加
ENGINE_DIR = Path(__file__).resolve().parent.parent / "engine"
sys.path.insert(0, str(ENGINE_DIR))

import structlog

# structlog 設定
structlog.configure(
    processors=[
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso"),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
        structlog.processors.JSONRenderer(),
    ],
    wrapper_class=structlog.make_filtering_bound_logger(logging.INFO),
    context_class=dict,
    logger_factory=structlog.PrintLoggerFactory(),
    cache_logger_on_first_use=True,
)

logger = structlog.get_logger("deepcast.scripts.autopilot")

JST = timezone(timedelta(hours=9))

# ログファイルパス
LOG_DIR = ENGINE_DIR / "data" / "logs"
LOG_DIR.mkdir(parents=True, exist_ok=True)


def _setup_file_logging() -> Path:
    """ファイルロギングをセットアップし、ログファイルパスを返す."""
    today = datetime.now(JST).strftime("%Y%m%d_%H%M%S")
    log_path = LOG_DIR / f"autopilot_{today}.log"
    # stdoutをファイルにもteeする
    return log_path


async def run(args: argparse.Namespace) -> int:
    """メイン実行関数. 終了コードを返す."""
    from autopilot import run_autopilot, _print_results

    exit_code = 0
    languages = ["ja", "en"] if args.both else [args.lang]

    for lang in languages:
        logger.info(
            "scripts.autopilot.start",
            language=lang,
            count=args.count,
            dry_run=args.dry_run,
        )

        try:
            results = await run_autopilot(
                language=lang,
                dry_run=args.dry_run,
                episode_count=args.count,
            )
            _print_results(results)

            # エラーがあれば終了コード1
            if results.get("errors"):
                exit_code = 1
                logger.warning(
                    "scripts.autopilot.errors",
                    language=lang,
                    errors=results["errors"],
                )

        except Exception as exc:
            logger.exception("scripts.autopilot.fatal", language=lang)
            print(f"\n[FATAL] {lang}: {exc}\n", file=sys.stderr)
            exit_code = 1

    return exit_code


def main() -> None:
    """CLIエントリーポイント."""
    parser = argparse.ArgumentParser(
        description="DeepCast AI 統合Autopilot — エピソード自動生成・公開",
    )
    parser.add_argument(
        "--both", action="store_true",
        help="日英両方のエピソードを生成",
    )
    parser.add_argument(
        "--dry-run", action="store_true",
        help="テスト実行（公開・アップロード・pushしない）",
    )
    parser.add_argument(
        "--count", type=int, default=1,
        help="1回あたりの生成エピソード数（デフォルト: 1）",
    )
    parser.add_argument(
        "--lang", type=str, default="ja",
        choices=["ja", "en"],
        help="言語（--both未指定時のみ有効）",
    )
    args = parser.parse_args()

    # UTF-8出力
    sys.stdout = io.TextIOWrapper(
        sys.stdout.buffer, encoding="utf-8", errors="replace",
    )

    # engine/ をカレントディレクトリに設定（設定ファイル等の相対パス解決のため）
    os.chdir(str(ENGINE_DIR))

    exit_code = asyncio.run(run(args))
    sys.exit(exit_code)


if __name__ == "__main__":
    main()

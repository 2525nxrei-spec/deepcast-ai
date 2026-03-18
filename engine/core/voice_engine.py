"""Deepcast Engine — ローカル TTS (Text-to-Speech) エンジン.

複数のローカル TTS バックエンドを統一インターフェースで操作し、
日本語・英語の自然な音声を外部 API なしで生成する。
"""

from __future__ import annotations

import asyncio
import hashlib
import re
import struct
import subprocess
import time
from enum import Enum
from pathlib import Path
from typing import Any

import structlog
from pydantic import BaseModel

from config.settings import settings
from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# Enums & Config
# ---------------------------------------------------------------------------


class TTSBackend(str, Enum):
    """サポートする TTS バックエンド."""

    GEMINI = "gemini"  # Gemini 2.5 Flash TTS (best quality, natural Japanese)
    COQUI = "coqui"  # Coqui TTS (XTTS-v2 for multilingual)
    STYLE_BERT = "style_bert"  # Style-BERT-VITS2 (best for Japanese)
    PIPER = "piper"  # Piper TTS (lightweight, fast)
    EDGE = "edge_tts"  # Edge TTS (offline-capable via edge-tts library)


class VoiceConfig(BaseModel):
    """TTS 合成パラメータ."""

    backend: TTSBackend = TTSBackend.EDGE
    language: str = "ja"
    speaker: str = "ja-JP-KeitaNeural"  # default Japanese voice
    speed: float = 1.0
    pitch: float = 1.0
    output_format: str = "mp3"  # mp3 or wav
    output_dir: str = "./data/audio"
    title: str = ""  # ファイル名に使用


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_CHUNK_SIZE: int = 500  # 長文分割の目安文字数

# Edge-TTS デフォルトボイスマップ
_EDGE_VOICES: dict[str, str] = {
    "ja": "ja-JP-KeitaNeural",
    "ja-male": "ja-JP-KeitaNeural",
    "en": "en-US-GuyNeural",
    "en-male": "en-US-GuyNeural",
    "en-gb": "en-GB-RyanNeural",
}

# Podcast スクリプト変換用プロンプト
_PODCAST_SYSTEM_PROMPT_JA = (
    "あなたは日本語ラジオ番組の台本ライターです。\n"
    "【絶対ルール】出力は必ず日本語のみ。英語で書くのは禁止。\n"
    "【形式】2人のパーソナリティ（ホストとアシスタント）の対話形式で書く。\n"
    "- ホスト（男性、渋めの40代）：話題を振り、深掘りする役。深夜ラジオDJのような落ち着いた雰囲気。博識で、意外な角度から話を展開する。\n"
    "- アシスタント（男性、明るい20代）：リスナー目線で質問したり、驚いたり共感する役。好奇心旺盛なお兄さん。鋭い疑問を投げかける。\n"
    "\n"
    "【内容の深さ — 最重要】\n"
    "- 表面的な解説で終わらせない。「へえ、知らなかった」とリスナーが思う情報を必ず含める\n"
    "- 具体的なデータ、研究結果、歴史的エピソード、実例を会話の中に自然に織り込む\n"
    "- 複数の分野をつなげる視点を入れる（「これ、実は心理学の〇〇とつながっていて」など）\n"
    "- 通説や常識に「実はそうでもないんです」と切り込む場面を作る\n"
    "- リスナーが聴いた後に考え方や行動を変えられるような実践的な示唆で締める\n"
    "- 抽象論だけで終わらせず、「たとえば〜」と具体例を必ず挟む\n"
    "\n"
    "【口調のルール】\n"
    "- ラジオ番組のような丁寧だけど堅すぎない口調（「ですます」調ベース）\n"
    "- 「ぶっちゃけ」「マジで」「ヤバい」は使わない\n"
    "- 代わりに「実はこれ、面白いんですよ」「へえ、そうなんですね！」「ここが重要なポイントで」のような自然な会話\n"
    "- 専門用語は対話の中で自然に説明する（アシスタントが「それってどういうことですか？」と聞く）\n"
    "- 間（ま）を意識して、聴きやすいテンポにする\n"
    "\n"
    "【フォーマット】\n"
    "ホスト: セリフ\n"
    "アシスタント: セリフ\n"
    "の形式で書く。名前の後にコロンをつけて改行する。\n"
    "- 出力はプレーンテキストのみ。マークダウンやHTMLタグは使わない\n"
    "- 1ターンのセリフは2〜3文程度。長すぎないこと。\n"
)

_PODCAST_SYSTEM_PROMPT_EN = (
    "You are a podcast script writer. "
    "Rewrite the given article in a natural, conversational tone. "
    "Explain jargon simply and make it easy to follow by ear. "
    "Output plain text only. No markdown or HTML tags."
)


# ---------------------------------------------------------------------------
# VoiceEngine
# ---------------------------------------------------------------------------


class VoiceEngine:
    """複数ローカル TTS バックエンドの統一インターフェース.

    Usage::

        engine = VoiceEngine()
        audio_path = await engine.synthesize("こんにちは、世界！")
        podcast_path = await engine.synthesize_podcast("タイトル", "記事本文...")
    """

    def __init__(self) -> None:
        self._llm = LLMClient()
        self._default_config = VoiceConfig(
            backend=TTSBackend(settings.TTS_BACKEND),
            output_dir=settings.TTS_OUTPUT_DIR,
        )
        logger.info(
            "voice_engine.initialized",
            default_backend=self._default_config.backend.value,
            output_dir=self._default_config.output_dir,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _ensure_output_dir(output_dir: str) -> Path:
        """出力ディレクトリを作成して Path を返す."""
        path = Path(output_dir)
        path.mkdir(parents=True, exist_ok=True)
        return path

    @staticmethod
    def _generate_filename(
        text: str, language: str, fmt: str,
        title: str = "",
    ) -> str:
        """わかりやすいファイル名を生成する.

        Format: ``{title_slug}_{timestamp}.{format}``
        タイトルがあればそれを使い、なければハッシュベース。
        """
        ts = int(time.time())
        if title:
            # タイトルからファイル名に使える部分を抽出（日本語OK）
            safe = re.sub(r'[\\/*?:"<>|]', '', title)[:40].strip()
            return f"{safe}_{ts}.{fmt}"
        h = hashlib.sha256(text.encode()).hexdigest()[:8]
        return f"{language}_{ts}_{h}.{fmt}"

    @staticmethod
    def _split_text(text: str, max_len: int = _CHUNK_SIZE) -> list[str]:
        """長文を文末区切りでチャンク分割する.

        句読点（。！？!?.）を優先的に区切り位置にする。
        """
        if len(text) <= max_len:
            return [text]

        chunks: list[str] = []
        remaining = text

        while remaining:
            if len(remaining) <= max_len:
                chunks.append(remaining)
                break

            # max_len 以内で最後の文末区切りを探す
            segment = remaining[:max_len]
            split_pos = -1
            for sep in ("。", "！", "？", "!", "?", ".", "\n"):
                pos = segment.rfind(sep)
                if pos > split_pos:
                    split_pos = pos

            if split_pos == -1:
                # 文末記号がなければスペースで分割
                split_pos = segment.rfind(" ")
            if split_pos == -1:
                # それでも見つからなければ max_len で強制分割
                split_pos = max_len - 1

            chunks.append(remaining[: split_pos + 1].strip())
            remaining = remaining[split_pos + 1 :].strip()

        return [c for c in chunks if c]

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize(
        self, text: str, config: VoiceConfig | None = None,
    ) -> Path:
        """テキストから音声を生成する.

        Args:
            text: 合成するテキスト.
            config: TTS 設定 (省略時はデフォルト).

        Returns:
            生成された音声ファイルのパス.
        """
        cfg = config or self._default_config
        logger.info(
            "voice_engine.synthesize.start",
            backend=cfg.backend.value,
            language=cfg.language,
            text_length=len(text),
        )

        dispatch = {
            TTSBackend.GEMINI: self._synthesize_gemini,
            TTSBackend.EDGE: self._synthesize_edge,
            TTSBackend.COQUI: self._synthesize_coqui,
            TTSBackend.STYLE_BERT: self._synthesize_style_bert,
            TTSBackend.PIPER: self._synthesize_piper,
        }

        handler = dispatch.get(cfg.backend, self._synthesize_edge)

        try:
            result = await handler(text, cfg)
        except Exception as exc:
            if cfg.backend != TTSBackend.EDGE:
                logger.warning(
                    "voice_engine.synthesize.fallback",
                    original_backend=cfg.backend.value,
                    error=str(exc),
                )
                fallback_cfg = cfg.model_copy(
                    update={"backend": TTSBackend.EDGE},
                )
                result = await self._synthesize_edge(text, fallback_cfg)
            else:
                raise

        logger.info(
            "voice_engine.synthesize.done",
            path=str(result),
        )
        return result

    async def synthesize_podcast(
        self,
        title: str,
        body: str,
        language: str = "ja",
    ) -> Path:
        """記事コンテンツをポッドキャスト音声に変換する.

        1. LLM で記事を話し言葉のスクリプトに変換
        2. イントロ・アウトロを追加
        3. TTS で音声合成

        Args:
            title: 記事タイトル.
            body: 記事本文.
            language: 言語コード ("ja" / "en").

        Returns:
            生成された音声ファイルのパス.
        """
        logger.info(
            "voice_engine.synthesize_podcast.start",
            title=title,
            language=language,
            body_length=len(body),
        )

        # --- Gemini API でスクリプト変換（高速） ---
        if language == "ja":
            full_prompt = _PODCAST_SYSTEM_PROMPT_JA + (
                f"\n以下の日本語記事を、日本語のポッドキャスト台本に変換してください。\n"
                f"英語は絶対に使わないでください。すべて日本語で出力してください。\n\n"
                f"タイトル: {title}\n\n"
                f"本文:\n{body}"
            )
        else:
            full_prompt = _PODCAST_SYSTEM_PROMPT_EN + (
                f"\nConvert the following article into a podcast script.\n\n"
                f"Title: {title}\n\n"
                f"Body:\n{body}"
            )

        # Gemini Flash で台本生成（ローカルLLMより圧倒的に高速）
        try:
            from google import genai
            client = genai.Client(api_key=settings.GEMINI_API_KEY)

            def _generate_script():
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt,
                )
                return response.text

            script = await asyncio.to_thread(_generate_script)
            logger.info("voice_engine.script.gemini_ok", script_length=len(script))
        except Exception as exc:
            # Gemini失敗時はローカルLLMにフォールバック
            logger.warning("voice_engine.script.gemini_failed", error=str(exc))
            script = await self._llm.generate(
                prompt=full_prompt,
                system_prompt="",
                temperature=0.7,
            )

        # --- イントロ・アウトロ追加 ---
        if language == "ja":
            intro = (
                f"ホスト: みなさん、こんにちは。DeepCastの時間です。今日は「{title}」について話していきましょう。\n"
                f"アシスタント: 楽しみですね！早速いきましょう。\n\n"
            )
            outro = (
                "\n\nホスト: ということで、今日はこのあたりで。いかがでしたか？\n"
                "アシスタント: すごく勉強になりました！リスナーのみなさんもぜひ考えてみてくださいね。\n"
                "ホスト: それでは、また次回のDeepCastでお会いしましょう。\n"
                "アシスタント: ありがとうございました！"
            )
        else:
            intro = (
                f"Welcome to DeepCast. Today we'll be covering: {title}.\n\n"
            )
            outro = (
                "\n\nThank you for listening to DeepCast. "
                "See you next time."
            )

        full_script = intro + script + outro

        # --- TTS向けテキストクリーニング ---
        # マークダウン記法、ハッシュ記号、URL等を除去（読み上げに不要なもの全て）
        full_script = re.sub(r'\*\*(.+?)\*\*', r'\1', full_script)  # **太字**
        full_script = re.sub(r'\*(.+?)\*', r'\1', full_script)  # *斜体*
        full_script = re.sub(r'`(.+?)`', r'\1', full_script)  # `コード`
        full_script = re.sub(r'https?://\S+', '', full_script)  # URL
        full_script = re.sub(r'#', '', full_script)  # #記号を全て除去
        full_script = re.sub(r'[-=]{3,}', '', full_script)  # --- や === 区切り線
        full_script = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', full_script)  # [リンク](url)
        full_script = re.sub(r'[>\-\*]\s', '', full_script)  # > 引用、- リスト
        full_script = re.sub(r'\n{3,}', '\n\n', full_script)  # 過剰な改行

        logger.debug(
            "voice_engine.synthesize_podcast.script_ready",
            script_length=len(full_script),
        )

        # --- 音声合成 ---
        backend = TTSBackend(settings.TTS_BACKEND)

        # Gemini TTS対話モード: ホスト/アシスタントを別ボイスで合成
        if backend == TTSBackend.GEMINI and "ホスト:" in full_script:
            return await self._synthesize_gemini_dialogue(full_script, language, title=title)

        # Edge-TTS対話モード: ホスト/アシスタントを別ボイスで合成
        if backend == TTSBackend.EDGE and "ホスト:" in full_script:
            return await self._synthesize_edge_dialogue(full_script, language, title=title)

        speaker = _EDGE_VOICES.get(language, _EDGE_VOICES["ja"])
        config = VoiceConfig(
            backend=backend,
            language=language,
            speaker=speaker,
            output_dir=settings.TTS_OUTPUT_DIR,
            title=title,
        )

        return await self.synthesize(full_script, config)

    async def list_available_voices(
        self, backend: TTSBackend | None = None,
    ) -> dict[str, Any]:
        """利用可能なボイス一覧を返す.

        Args:
            backend: 特定バックエンドのみ取得 (None で全バックエンド).

        Returns:
            バックエンド名をキーとしたボイス情報の辞書.
        """
        voices: dict[str, Any] = {}

        if backend is None or backend == TTSBackend.EDGE:
            voices["edge_tts"] = {
                "voices": [
                    {"name": "ja-JP-KeitaNeural", "language": "ja", "gender": "male", "quality": "high"},
                    {"name": "en-US-GuyNeural", "language": "en", "gender": "male", "quality": "high"},
                    {"name": "en-GB-RyanNeural", "language": "en-gb", "gender": "male", "quality": "high"},
                ],
                "note": "Full list available via `edge-tts --list-voices`",
            }

        if backend is None or backend == TTSBackend.COQUI:
            voices["coqui"] = {
                "voices": [
                    {"name": "XTTS-v2", "language": "multilingual", "quality": "very_high"},
                ],
                "note": "Clone voices with reference audio. Requires GPU.",
            }

        if backend is None or backend == TTSBackend.STYLE_BERT:
            voices["style_bert"] = {
                "voices": [
                    {"name": "default", "language": "ja", "quality": "very_high"},
                ],
                "note": f"Local server required at {settings.STYLE_BERT_URL}",
            }

        if backend is None or backend == TTSBackend.PIPER:
            voices["piper"] = {
                "voices": [
                    {"name": "ja_JP-tohoku-medium", "language": "ja", "quality": "medium"},
                    {"name": "en_US-lessac-medium", "language": "en", "quality": "medium"},
                    {"name": "en_US-libritts-high", "language": "en", "quality": "high"},
                ],
                "note": "Models auto-downloaded on first use.",
            }

        return voices

    async def check_backends(self) -> dict[str, bool]:
        """インストール済み TTS バックエンドの可用性をチェックする.

        Returns:
            バックエンド名をキーとした可用性フラグの辞書.
        """
        results: dict[str, bool] = {}

        # edge-tts
        try:
            import edge_tts  # noqa: F401

            results["edge_tts"] = True
        except ImportError:
            results["edge_tts"] = False

        # Coqui TTS
        try:
            from TTS.api import TTS as CoquiTTS  # noqa: F401

            results["coqui"] = True
        except ImportError:
            results["coqui"] = False

        # Style-BERT-VITS2 (check if server is running)
        try:
            import httpx

            async with httpx.AsyncClient(timeout=3.0) as client:
                resp = await client.get(f"{settings.STYLE_BERT_URL}/")
                results["style_bert"] = resp.status_code == 200
        except Exception:
            results["style_bert"] = False

        # Piper
        try:
            import piper  # noqa: F401

            results["piper"] = True
        except ImportError:
            # piper-tts uses a different import path sometimes
            try:
                import piper_phonemize  # noqa: F401

                results["piper"] = True
            except ImportError:
                results["piper"] = False

        logger.info("voice_engine.check_backends", **results)
        return results

    # ------------------------------------------------------------------
    # Backend implementations
    # ------------------------------------------------------------------

    async def _synthesize_edge(
        self, text: str, config: VoiceConfig,
    ) -> Path:
        """edge-tts バックエンドで音声合成する.

        Args:
            text: 合成テキスト.
            config: TTS 設定.

        Returns:
            音声ファイルのパス.
        """
        import edge_tts

        out_dir = self._ensure_output_dir(config.output_dir)
        filename = self._generate_filename(text, config.language, config.output_format, title=config.title)
        out_path = out_dir / filename

        # rate / pitch を edge-tts 形式に変換
        rate_pct = int((config.speed - 1.0) * 100)
        rate_str = f"{rate_pct:+d}%"
        pitch_hz = int((config.pitch - 1.0) * 50)
        pitch_str = f"{pitch_hz:+d}Hz"

        chunks = self._split_text(text)
        logger.debug(
            "voice_engine.edge.synthesize",
            voice=config.speaker,
            chunks=len(chunks),
            rate=rate_str,
            pitch=pitch_str,
        )

        if len(chunks) == 1:
            communicate = edge_tts.Communicate(
                text=chunks[0],
                voice=config.speaker,
                rate=rate_str,
                pitch=pitch_str,
            )
            await communicate.save(str(out_path))
        else:
            # 複数チャンクを個別に合成してから結合
            temp_paths: list[Path] = []
            for i, chunk in enumerate(chunks):
                tmp = out_dir / f"_tmp_{filename}_{i}.{config.output_format}"
                communicate = edge_tts.Communicate(
                    text=chunk,
                    voice=config.speaker,
                    rate=rate_str,
                    pitch=pitch_str,
                )
                await communicate.save(str(tmp))
                temp_paths.append(tmp)

            await self._concat_audio_files(temp_paths, out_path, config.output_format)

            # 一時ファイル削除
            for tmp in temp_paths:
                tmp.unlink(missing_ok=True)

        logger.info("voice_engine.edge.done", path=str(out_path))
        return out_path

    async def _synthesize_edge_dialogue(
        self, script: str, language: str, title: str = "",
    ) -> Path:
        """Edge-TTSで対話形式の台本を2ボイスで合成する.

        「ホスト: セリフ」→ Enceladus（渋め）、「アシスタント: セリフ」→ Zephyr（明るめ）で
        各セリフを個別に合成し、結合して1つのMP3にする。
        """
        import edge_tts

        voice_map = {
            "ja": {"ホスト": "ja-JP-KeitaNeural", "アシスタント": "ja-JP-KeitaNeural"},
            "en": {"ホスト": "en-US-GuyNeural", "アシスタント": "en-US-GuyNeural"},
        }
        voices = voice_map.get(language, voice_map["ja"])

        # 台本をセリフ単位にパース
        lines: list[tuple[str, str]] = []  # (voice_name, text)
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("ホスト:") or line.startswith("ホスト："):
                text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if text:
                    lines.append((voices["ホスト"], text))
            elif line.startswith("アシスタント:") or line.startswith("アシスタント："):
                text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if text:
                    lines.append((voices["アシスタント"], text))
            else:
                # ラベルなし行は直前の話者を継続、なければホスト
                voice = lines[-1][0] if lines else voices["ホスト"]
                lines.append((voice, line))

        if not lines:
            logger.warning("voice_engine.dialogue.no_lines")
            lines = [(voices["ホスト"], script)]

        out_dir = self._ensure_output_dir(settings.TTS_OUTPUT_DIR)
        ts = int(time.time() * 1000)
        if title:
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:40].strip()
            final_path = out_dir / f"{safe_title}_{ts}.mp3"
        else:
            final_path = out_dir / f"dialogue_{ts}.mp3"
        temp_paths: list[Path] = []

        logger.info(
            "voice_engine.edge_dialogue.start",
            lines=len(lines),
            language=language,
        )

        for i, (voice, text) in enumerate(lines):
            tmp = out_dir / f"_dlg_{ts}_{i:04d}.mp3"
            comm = edge_tts.Communicate(text=text, voice=voice, rate="-5%")
            await comm.save(str(tmp))
            temp_paths.append(tmp)

        await self._concat_audio_files(temp_paths, final_path, "mp3")

        for tmp in temp_paths:
            tmp.unlink(missing_ok=True)

        logger.info("voice_engine.edge_dialogue.done", path=str(final_path), segments=len(lines))
        return final_path

    async def _synthesize_gemini_dialogue(
        self, script: str, language: str, title: str = "",
    ) -> Path:
        """Gemini TTS で対話形式の台本を2ボイスで合成する.

        ホスト → Enceladus（低め渋い40代男性DJ）、
        アシスタント → Zephyr（明るく好奇心旺盛な若い男性）で
        各セリフを個別に合成し、loudnorm + silence挿入 + atempo で仕上げる。
        """
        from google import genai

        # --- 台本をセリフ単位にパース ---
        segments: list[tuple[str, str]] = []  # (role, text)
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("ホスト:") or line.startswith("ホスト："):
                text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if text:
                    segments.append(("host", text))
            elif line.startswith("アシスタント:") or line.startswith("アシスタント："):
                text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if text:
                    segments.append(("assistant", text))
            else:
                # ラベルなし行は直前の話者を継続、なければホスト
                role = segments[-1][0] if segments else "host"
                segments.append((role, line))

        if not segments:
            logger.warning("voice_engine.gemini_dialogue.no_lines")
            segments = [("host", script)]

        logger.info(
            "voice_engine.gemini_dialogue.start",
            lines=len(segments),
            language=language,
        )

        # --- 出力パス ---
        out_dir = self._ensure_output_dir(settings.TTS_OUTPUT_DIR)
        ts = int(time.time() * 1000)
        if title:
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:40].strip()
            final_filename = f"{safe_title}_{ts}.mp3"
        else:
            final_filename = f"dialogue_{ts}.mp3"
        final_path = out_dir / final_filename

        # --- ボイス設定 ---
        voice_config = {
            "host": {
                "voice_name": "Enceladus",
                "prompt_prefix": "以下のセリフを、低めで渋い40代男性の深夜ラジオDJのように、落ち着いて語りかけるように読んでください。\n\n",
            },
            "assistant": {
                "voice_name": "Zephyr",
                "prompt_prefix": "以下のセリフを、明るく好奇心旺盛な若い男性として、テンポよく読んでください。\n\n",
            },
        }

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        temp_wav_paths: list[Path] = []
        temp_mp3_paths: list[Path] = []

        try:
            # --- 各セリフを個別にTTS合成 ---
            for i, (role, text) in enumerate(segments):
                vc = voice_config[role]
                tts_prompt = vc["prompt_prefix"] + text

                def _tts_segment(prompt: str, vname: str, seg_path: Path) -> None:
                    response = client.models.generate_content(
                        model="gemini-2.5-flash-preview-tts",
                        contents=prompt,
                        config=genai.types.GenerateContentConfig(
                            response_modalities=["AUDIO"],
                            speech_config=genai.types.SpeechConfig(
                                voice_config=genai.types.VoiceConfig(
                                    prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                                        voice_name=vname,
                                    )
                                )
                            ),
                        ),
                    )
                    if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                        raise RuntimeError(f"Gemini TTS returned empty response for segment {i}")
                    audio_data = response.candidates[0].content.parts[0].inline_data.data
                    # PCM 24000Hz mono 16bit → WAV
                    data_size = len(audio_data)
                    header = struct.pack(
                        '<4sI4s4sIHHIIHH4sI',
                        b'RIFF', 36 + data_size, b'WAVE',
                        b'fmt ', 16, 1, 1, 24000, 24000 * 2, 2, 16,
                        b'data', data_size,
                    )
                    seg_path.write_bytes(header + audio_data)

                wav_path = out_dir / f"_gemtts_{ts}_{i:04d}.wav"
                await asyncio.to_thread(
                    _tts_segment, tts_prompt, vc["voice_name"], wav_path,
                )
                temp_wav_paths.append(wav_path)

                logger.debug(
                    "voice_engine.gemini_dialogue.segment_done",
                    segment=i,
                    role=role,
                )

            # --- ffmpeg: 各WAVセグメントをMP3に変換（loudnorm + フィルタ） ---
            for wav_path in temp_wav_paths:
                mp3_path = wav_path.with_suffix(".mp3")
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg", "-y", "-i", str(wav_path),
                        "-af", "highpass=f=80,lowpass=f=12000,loudnorm=I=-16:TP=-1.5:LRA=11",
                        "-ar", "44100", "-b:a", "192k",
                        str(mp3_path),
                    ],
                    capture_output=True,
                )
                if result.returncode != 0:
                    logger.warning(
                        "voice_engine.gemini_dialogue.ffmpeg_convert_failed",
                        error=result.stderr.decode("utf-8", errors="replace")[:500],
                    )
                temp_mp3_paths.append(mp3_path)

            # --- 0.5秒の無音MP3を生成 ---
            silence_path = out_dir / f"_gemtts_{ts}_silence.mp3"
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=44100:cl=mono",
                    "-t", "0.5", "-b:a", "192k",
                    str(silence_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                logger.warning(
                    "voice_engine.gemini_dialogue.silence_failed",
                    error=result.stderr.decode("utf-8", errors="replace")[:500],
                )

            # --- concat リスト作成（セグメント間に無音挿入） ---
            concat_list_path = out_dir / f"_gemtts_{ts}_concat.txt"
            concat_lines: list[str] = []
            for j, mp3_path in enumerate(temp_mp3_paths):
                concat_lines.append(f"file '{mp3_path.resolve().as_posix()}'")
                if j < len(temp_mp3_paths) - 1:
                    concat_lines.append(f"file '{silence_path.resolve().as_posix()}'")
            concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

            # --- concat → atempo で最終出力 ---
            concat_tmp = out_dir / f"_gemtts_{ts}_concat.mp3"
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_path),
                    "-af", "atempo=1.08",
                    "-b:a", "192k", "-ar", "44100",
                    str(final_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                logger.error(
                    "voice_engine.gemini_dialogue.concat_failed",
                    error=error_msg[:500],
                )
                raise RuntimeError(f"ffmpeg concat failed: {error_msg[:200]}")

        finally:
            # --- 一時ファイル削除 ---
            cleanup_paths = (
                temp_wav_paths
                + temp_mp3_paths
                + [
                    out_dir / f"_gemtts_{ts}_silence.mp3",
                    out_dir / f"_gemtts_{ts}_concat.txt",
                    out_dir / f"_gemtts_{ts}_concat.mp3",
                ]
            )
            for p in cleanup_paths:
                try:
                    p.unlink(missing_ok=True)
                except Exception:
                    pass

        logger.info(
            "voice_engine.gemini_dialogue.done",
            path=str(final_path),
            segments=len(segments),
        )
        return final_path

    async def _synthesize_coqui(
        self, text: str, config: VoiceConfig,
    ) -> Path:
        """Coqui TTS (XTTS-v2) バックエンドで音声合成する.

        Args:
            text: 合成テキスト.
            config: TTS 設定.

        Returns:
            音声ファイルのパス.
        """
        from TTS.api import TTS as CoquiTTS

        out_dir = self._ensure_output_dir(config.output_dir)
        filename = self._generate_filename(text, config.language, "wav")
        out_path = out_dir / filename

        logger.debug(
            "voice_engine.coqui.synthesize",
            language=config.language,
        )

        # Coqui TTS は同期 API なので別スレッドで実行
        def _run() -> None:
            tts = CoquiTTS("tts_models/multilingual/multi-dataset/xtts_v2")
            tts.tts_to_file(
                text=text,
                file_path=str(out_path),
                language=config.language,
                speed=config.speed,
            )

        await asyncio.to_thread(_run)

        # wav → mp3 変換が必要な場合
        if config.output_format == "mp3":
            mp3_path = out_path.with_suffix(".mp3")
            await self._convert_wav_to_mp3(out_path, mp3_path)
            out_path.unlink(missing_ok=True)
            out_path = mp3_path

        logger.info("voice_engine.coqui.done", path=str(out_path))
        return out_path

    async def _synthesize_style_bert(
        self, text: str, config: VoiceConfig,
    ) -> Path:
        """Style-BERT-VITS2 ローカルサーバーで音声合成する.

        サーバーが起動していない場合は edge-tts にフォールバックする。

        Args:
            text: 合成テキスト.
            config: TTS 設定.

        Returns:
            音声ファイルのパス.
        """
        import httpx

        base_url = settings.STYLE_BERT_URL
        out_dir = self._ensure_output_dir(config.output_dir)
        filename = self._generate_filename(text, config.language, config.output_format, title=config.title)
        out_path = out_dir / filename

        logger.debug(
            "voice_engine.style_bert.synthesize",
            base_url=base_url,
        )

        try:
            async with httpx.AsyncClient(timeout=60.0) as client:
                params = {
                    "text": text,
                    "model_id": 0,
                    "speaker_id": 0,
                    "sdp_ratio": 0.2,
                    "noise": 0.6,
                    "noisew": 0.8,
                    "length": 1.0 / config.speed if config.speed > 0 else 1.0,
                    "language": "JP" if config.language == "ja" else "EN",
                    "auto_split": True,
                    "split_interval": 0.5,
                }
                resp = await client.get(
                    f"{base_url}/voice",
                    params=params,
                )
                resp.raise_for_status()

                out_path.write_bytes(resp.content)
                logger.info("voice_engine.style_bert.done", path=str(out_path))
                return out_path

        except Exception as exc:
            logger.warning(
                "voice_engine.style_bert.unavailable",
                error=str(exc),
                fallback="edge_tts",
            )
            # edge-tts にフォールバック
            fallback_cfg = config.model_copy(
                update={"backend": TTSBackend.EDGE},
            )
            return await self._synthesize_edge(text, fallback_cfg)

    async def _synthesize_piper(
        self, text: str, config: VoiceConfig,
    ) -> Path:
        """Piper TTS バックエンドで音声合成する.

        Args:
            text: 合成テキスト.
            config: TTS 設定.

        Returns:
            音声ファイルのパス.
        """
        out_dir = self._ensure_output_dir(config.output_dir)
        filename = self._generate_filename(text, config.language, "wav")
        out_path = out_dir / filename

        # 言語に応じたモデル選択
        model_map = {
            "ja": "ja_JP-tohoku-medium",
            "en": "en_US-lessac-medium",
        }
        model_name = model_map.get(config.language, "en_US-lessac-medium")

        logger.debug(
            "voice_engine.piper.synthesize",
            model=model_name,
        )

        # piper-tts CLI を subprocess で実行
        # (piper の Python API はプラットフォーム依存のため CLI 経由が安定)
        cmd = [
            "piper",
            "--model", model_name,
            "--output_file", str(out_path),
            "--length_scale", str(1.0 / config.speed if config.speed > 0 else 1.0),
        ]

        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdin=asyncio.subprocess.PIPE,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        stdout, stderr = await process.communicate(input=text.encode("utf-8"))

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            raise RuntimeError(
                f"Piper TTS failed (exit {process.returncode}): {error_msg}"
            )

        # wav → mp3 変換が必要な場合
        if config.output_format == "mp3":
            mp3_path = out_path.with_suffix(".mp3")
            await self._convert_wav_to_mp3(out_path, mp3_path)
            out_path.unlink(missing_ok=True)
            out_path = mp3_path

        logger.info("voice_engine.piper.done", path=str(out_path))
        return out_path

    async def _synthesize_gemini(
        self, text: str, config: VoiceConfig,
    ) -> Path:
        """Gemini 2.5 Flash TTS で音声合成する（最も自然な日本語音声）.

        Args:
            text: 合成テキスト.
            config: TTS 設定.

        Returns:
            音声ファイルのパス.
        """
        import struct
        from google import genai

        out_dir = self._ensure_output_dir(config.output_dir)
        filename = self._generate_filename(text, config.language, "wav", title=getattr(config, '_title', ''))
        out_path = out_dir / filename

        logger.debug(
            "voice_engine.gemini.synthesize",
            language=config.language,
        )

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        tts_prompt = f"以下のテキストを、落ち着いた声でそのまま読み上げてください。\n\n{text}"

        def _run():
            response = client.models.generate_content(
                model="gemini-2.5-flash-preview-tts",
                contents=tts_prompt,
                config=genai.types.GenerateContentConfig(
                    response_modalities=["AUDIO"],
                    speech_config=genai.types.SpeechConfig(
                        voice_config=genai.types.VoiceConfig(
                            prebuilt_voice_config=genai.types.PrebuiltVoiceConfig(
                                voice_name="Charon"
                            )
                        )
                    ),
                ),
            )
            if not response.candidates or not response.candidates[0].content or not response.candidates[0].content.parts:
                raise RuntimeError("Gemini TTS returned empty response")
            audio_data = response.candidates[0].content.parts[0].inline_data.data
            # PCM → WAV変換
            data_size = len(audio_data)
            header = struct.pack('<4sI4s4sIHHIIHH4sI',
                b'RIFF', 36 + data_size, b'WAVE',
                b'fmt ', 16, 1, 1, 24000, 24000 * 2, 2, 16,
                b'data', data_size)
            out_path.write_bytes(header + audio_data)

        await asyncio.to_thread(_run)

        # wav → mp3 変換
        if config.output_format == "mp3":
            mp3_path = out_path.with_suffix(".mp3")
            await self._convert_wav_to_mp3(out_path, mp3_path)
            out_path.unlink(missing_ok=True)
            out_path = mp3_path

        logger.info("voice_engine.gemini.done", path=str(out_path))
        return out_path

    # ------------------------------------------------------------------
    # Audio utilities
    # ------------------------------------------------------------------

    @staticmethod
    async def _convert_wav_to_mp3(wav_path: Path, mp3_path: Path) -> None:
        """ffmpeg で WAV → MP3 変換する."""
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-i", str(wav_path),
            "-codec:a", "libmp3lame", "-qscale:a", "2",
            str(mp3_path),
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
        _, stderr = await process.communicate()

        if process.returncode != 0:
            error_msg = stderr.decode("utf-8", errors="replace")
            logger.warning(
                "voice_engine.convert_mp3.failed",
                error=error_msg,
            )
            # ffmpeg がなければ wav のまま残す
            raise RuntimeError(f"ffmpeg conversion failed: {error_msg}")

    @staticmethod
    async def _concat_audio_files(
        input_paths: list[Path], output_path: Path, fmt: str,
    ) -> None:
        """複数の音声ファイルを ffmpeg で結合する."""
        if not input_paths:
            return

        if len(input_paths) == 1:
            import shutil
            shutil.copy2(str(input_paths[0]), str(output_path))
            return

        # ffmpeg concat demuxer 用のリストファイルを作成
        list_file = output_path.parent / f"_concat_{output_path.stem}.txt"
        try:
            list_content = "\n".join(
                f"file '{p.resolve().as_posix()}'" for p in input_paths
            )
            list_file.write_text(list_content, encoding="utf-8")

            process = await asyncio.create_subprocess_exec(
                "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                "-i", str(list_file),
                "-c", "copy",
                str(output_path),
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE,
            )
            _, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr.decode("utf-8", errors="replace")
                logger.warning(
                    "voice_engine.concat.failed",
                    error=error_msg,
                )
                # 結合失敗時は最初のチャンクだけコピー
                import shutil
                shutil.copy2(str(input_paths[0]), str(output_path))
        finally:
            list_file.unlink(missing_ok=True)

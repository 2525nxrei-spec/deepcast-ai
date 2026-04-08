"""Deepcast Engine — Gemini TTS 音声エンジン.

Gemini 2.5 Flash TTS のみを使用して、
メインパーソナリティ（山口）とサブパーソナリティ（田中）の
2人構成3分ポッドキャスト音声を生成する。
"""

from __future__ import annotations

import asyncio
import re
import shutil
import struct
import subprocess
import time
from pathlib import Path
from typing import Any

import structlog
from google import genai

from config.settings import settings
from core.llm_client import LLMClient

logger = structlog.get_logger(__name__)


# ---------------------------------------------------------------------------
# ポッドキャスト台本生成プロンプト
# ---------------------------------------------------------------------------

_PODCAST_SCRIPT_PROMPT_JA = (
    "あなたは日本語ポッドキャストの台本ライターです。\n"
    "【絶対ルール】出力は必ず日本語のみ。英語禁止。\n\n"
    "【エピソード構成 — 全3分（180秒）厳守】\n"
    "2人のパーソナリティで構成します。\n"
    "※イントロ・アウトロは別途追加されるため、本文は合計2分30秒分で書くこと。\n\n"
    "■ 前半（75秒 = 約280〜320文字）: メインパーソナリティ「山口」\n"
    "- トピックの導入→核心の解説→意外な事実やデータ\n"
    "- 聞き手を引き込むフックから始める\n\n"
    "■ ブリッジ（切り替え・1文ずつ）:\n"
    "山口: ここからは田中さんにバトンタッチしましょう。\n"
    "田中: はい、ここからは私がお伝えします。\n\n"
    "■ 後半（75秒 = 約280〜320文字）: サブパーソナリティ「田中」\n"
    "- 別の角度からの考察、実践的な示唆\n"
    "- リスナーが明日から使える知見で締める\n\n"
    "【パーソナリティ設定】\n"
    "- 山口（40代男性）：低めの声、落ち着いた雰囲気。博識。\n"
    "- 田中（20代男性）：明るく好奇心旺盛。リスナー目線。\n\n"
    "【文字数 — 厳守（最重要）】\n"
    "- 山口パート: 250〜290文字（絶対に300文字を超えない）\n"
    "- 田中パート: 250〜290文字（絶対に300文字を超えない）\n"
    "- 合計: 500〜580文字（これを超えると尺オーバーになる）\n"
    "- 短すぎるより少し短めが理想。580文字を超えたら削ること\n\n"
    "【口調】\n"
    "- 丁寧だけど堅すぎない「ですます」調\n"
    "- 「ぶっちゃけ」「マジで」「ヤバい」禁止\n"
    "- 専門用語は直後に噛み砕いた説明\n\n"
    "【フォーマット】\n"
    "山口: セリフ\n"
    "田中: セリフ\n"
    "の形式。プレーンテキストのみ。マークダウン・HTMLタグ禁止。\n"
    "挨拶は時間帯非依存（「こんにちは」OK、「こんばんは」NG）。\n"
)

_PODCAST_SCRIPT_PROMPT_EN = (
    "You are a podcast script writer.\n"
    "Structure: 3 minutes total (intro/outro added separately, write 2:30 of content).\n"
    "First 75s: Yamaguchi (main host, calm 40s male).\n"
    "Bridge: natural handoff (1 sentence each).\n"
    "Last 75s: Tanaka (sub host, bright 20s male).\n"
    "Yamaguchi: 140-160 words. Tanaka: 140-160 words. Total: 280-320 words MAX (STRICT).\n"
    "Format: 'Yamaguchi: line' and 'Tanaka: line'. Plain text only.\n"
)


# ---------------------------------------------------------------------------
# VoiceEngine
# ---------------------------------------------------------------------------


class VoiceEngine:
    """Gemini TTS のみを使用した音声エンジン.

    Usage::

        engine = VoiceEngine()
        audio_path = await engine.synthesize_podcast("タイトル", "記事本文...")
    """

    def __init__(self) -> None:
        self._llm = LLMClient()
        logger.info(
            "voice_engine.initialized",
            backend="gemini_tts_only",
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
    def _clean_script(script: str) -> str:
        """TTS向けにスクリプトをクリーニングする."""
        # マークダウン記法除去
        script = re.sub(r'\*\*(.+?)\*\*', r'\1', script)
        script = re.sub(r'\*(.+?)\*', r'\1', script)
        script = re.sub(r'`(.+?)`', r'\1', script)
        script = re.sub(r'https?://\S+', '', script)
        script = re.sub(r'#', '', script)
        script = re.sub(r'[-=]{3,}', '', script)
        script = re.sub(r'\[(.+?)\]\(.+?\)', r'\1', script)
        script = re.sub(r'[>\-\*]\s', '', script)
        script = re.sub(r'\n{3,}', '\n\n', script)
        return script.strip()

    @staticmethod
    def _parse_dialogue(script: str) -> list[tuple[str, str]]:
        """台本をパースして (role, text) のリストを返す.

        role: "host" (山口/Yamaguchi) or "sub" (田中/Tanaka)
        """
        segments: list[tuple[str, str]] = []
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("山口:") or line.startswith("山口：") or line.startswith("Yamaguchi:"):
                text = re.split(r'[:：]', line, maxsplit=1)[1].strip()
                if text:
                    segments.append(("host", text))
            elif line.startswith("田中:") or line.startswith("田中：") or line.startswith("Tanaka:"):
                text = re.split(r'[:：]', line, maxsplit=1)[1].strip()
                if text:
                    segments.append(("sub", text))
            else:
                role = segments[-1][0] if segments else "host"
                segments.append((role, line))
        return segments

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def synthesize(
        self, text: str, config: Any = None,
    ) -> Path:
        """単一テキストをGemini TTSで合成する."""
        out_dir = self._ensure_output_dir(settings.TTS_OUTPUT_DIR)
        ts = int(time.time() * 1000)
        final_path = out_dir / f"single_{ts}.mp3"

        await self._gemini_tts_to_mp3(
            text=text,
            voice_name="Enceladus",
            prompt_prefix="以下のテキストを落ち着いた声で読み上げてください。\n\n",
            output_path=final_path,
        )
        return final_path

    async def synthesize_podcast(
        self,
        title: str,
        body: str,
        language: str = "ja",
    ) -> Path:
        """記事コンテンツを3分ポッドキャスト音声に変換する.

        1. Gemini Flash で台本生成（前半山口90秒 + ブリッジ + 後半田中90秒）
        2. 山口パート → Enceladus ボイス
        3. 田中パート → Zephyr ボイス
        4. 無音を挟んで結合、合計3分のMP3を出力
        5. 音声長バリデーション（175-185秒、最大3回リトライ）

        Args:
            title: 記事タイトル.
            body: 記事本文.
            language: 言語コード ("ja" / "en").

        Returns:
            生成された音声ファイルのパス.
        """
        # 最大3回リトライで175-185秒の範囲を目指す
        char_adjustment = 0  # プロンプト文字数の調整値
        for attempt in range(3):
            result_path = await self._synthesize_podcast_internal(
                title=title, body=body, language=language,
                char_adjustment=char_adjustment,
            )
            duration = await self._get_audio_duration(result_path)
            if duration is None:
                logger.warning("voice_engine.duration_unknown, accepting result")
                return result_path

            logger.info(
                "voice_engine.duration_validation",
                attempt=attempt + 1,
                duration=duration,
                char_adjustment=char_adjustment,
            )

            # 175-185秒の範囲内ならOK
            if 175 <= duration <= 185:
                logger.info("voice_engine.duration_accepted", duration=duration)
                return result_path

            # 最終リトライならそのまま返す
            if attempt >= 2:
                logger.warning(
                    "voice_engine.max_retries_reached",
                    final_duration=duration,
                )
                return result_path

            # プロンプト文字数を調整して再生成
            # 180秒からのズレに基づいて文字数を調整
            # 日本語: 約3.8文字/秒、英語: 約2.3語/秒
            diff_seconds = duration - 180
            if language == "ja":
                # 1秒あたり約3.8文字として調整
                char_adjustment = -int(diff_seconds * 3.8)
            else:
                # 英語: 1秒あたり約2.3語
                char_adjustment = -int(diff_seconds * 2.3)

            logger.info(
                "voice_engine.retrying_with_adjustment",
                attempt=attempt + 1,
                duration=duration,
                char_adjustment=char_adjustment,
            )
            # 前回生成ファイルを削除
            result_path.unlink(missing_ok=True)

        return result_path  # ここには到達しないが型安全のため

    async def _synthesize_podcast_internal(
        self,
        title: str,
        body: str,
        language: str = "ja",
        char_adjustment: int = 0,
    ) -> Path:
        """synthesize_podcastの内部実装（再生成制御用）.

        Args:
            char_adjustment: プロンプトの目標文字数を調整する値。
                             負の値=短くする（尺が長すぎた場合）、
                             正の値=長くする（尺が短すぎた場合）。
        """
        logger.info(
            "voice_engine.synthesize_podcast.start",
            title=title,
            language=language,
            body_length=len(body),
        )

        # --- Step 1: 台本生成 (Gemini Flash) ---
        # 文字数調整がある場合、プロンプトに追加指示を入れる
        adjustment_note = ""
        if char_adjustment != 0:
            if language == "ja":
                if char_adjustment < 0:
                    adjustment_note = (
                        f"\n【重要】前回の生成で音声が長すぎました。"
                        f"合計文字数を{abs(char_adjustment)}文字ほど減らしてください。"
                        f"特に各パートの文字数を均等に削減すること。\n"
                    )
                else:
                    adjustment_note = (
                        f"\n【重要】前回の生成で音声が短すぎました。"
                        f"合計文字数を{abs(char_adjustment)}文字ほど増やしてください。"
                        f"特に各パートの文字数を均等に増加すること。\n"
                    )
            else:
                if char_adjustment < 0:
                    adjustment_note = (
                        f"\n[IMPORTANT] Previous generation was too long. "
                        f"Reduce total word count by approximately {abs(char_adjustment)} words.\n"
                    )
                else:
                    adjustment_note = (
                        f"\n[IMPORTANT] Previous generation was too short. "
                        f"Increase total word count by approximately {abs(char_adjustment)} words.\n"
                    )

        if language == "ja":
            full_prompt = _PODCAST_SCRIPT_PROMPT_JA + adjustment_note + (
                f"\n以下の記事を3分間のポッドキャスト台本に変換してください。\n"
                f"英語は絶対に使わないでください。\n\n"
                f"タイトル: {title}\n\n"
                f"本文:\n{body}"
            )
        else:
            full_prompt = _PODCAST_SCRIPT_PROMPT_EN + adjustment_note + (
                f"\nConvert to a 3-minute podcast script.\n\n"
                f"Title: {title}\n\nBody:\n{body}"
            )

        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        try:
            def _generate_script():
                response = client.models.generate_content(
                    model="gemini-2.5-flash",
                    contents=full_prompt,
                )
                return response.text

            script = await asyncio.wait_for(
                asyncio.to_thread(_generate_script), timeout=60
            )
            logger.info("voice_engine.script.done", script_length=len(script))
        except Exception as exc:
            logger.error("voice_engine.script.failed", error=str(exc))
            raise

        # --- イントロ・アウトロ追加 ---
        if language == "ja":
            intro = (
                f"山口: みなさん、こんにちは。DeepCastの時間です。"
                f"今日は「{title}」についてお話しします。\n\n"
            )
            outro = (
                "\n\n山口: 今日はこのあたりで。また次回のDeepCastでお会いしましょう。\n"
                "田中: ありがとうございました！"
            )
        else:
            intro = (
                f"Yamaguchi: Welcome to DeepCast. Today we'll cover: {title}.\n\n"
            )
            outro = (
                "\n\nYamaguchi: That's all for today. See you next time on DeepCast.\n"
                "Tanaka: Thanks for listening!"
            )

        full_script = self._clean_script(intro + script + outro)

        logger.debug(
            "voice_engine.script_ready",
            script_length=len(full_script),
        )

        # --- Step 2: 台本をパースしてセグメント化 ---
        segments = self._parse_dialogue(full_script)

        if not segments:
            logger.warning("voice_engine.no_segments, using whole script as host")
            segments = [("host", full_script)]

        # Gemini TTS: 台本分割方式で合成（長尺の品質劣化を防止）
        # Gemini TTSが失敗した場合はリトライ（Edge TTSフォールバック無効）
        if backend == TTSBackend.GEMINI and "山口:" in full_script:
            max_tts_retries = 3
            for attempt in range(max_tts_retries):
                try:
                    return await self._synthesize_gemini_chunked(full_script, language, title=title)
                except (asyncio.TimeoutError, Exception) as e:
                    logger.warning(
                        "voice_engine.gemini_retry",
                        error=str(e),
                        attempt=attempt + 1,
                        max_retries=max_tts_retries,
                    )
                    if attempt < max_tts_retries - 1:
                        await asyncio.sleep(5)
                    else:
                        raise RuntimeError(f"Gemini TTS failed after {max_tts_retries} attempts: {e}")

        # 同一話者の連続セリフをバッチ化
        batched: list[tuple[str, str]] = []
        for role, text in segments:
            if batched and batched[-1][0] == role:
                batched[-1] = (role, batched[-1][1] + "\n" + text)
            else:
                batched.append((role, text))

        logger.info(
            "voice_engine.segments",
            total_batches=len(batched),
            host_count=sum(1 for r, _ in batched if r == "host"),
            sub_count=sum(1 for r, _ in batched if r == "sub"),
        )

        # --- Step 3: 各セグメントを話者別ボイスでTTS ---
        voice_config = {
            "host": {
                "voice_name": "Enceladus",
                "prompt_prefix": (
                    "以下のセリフを、低めで渋い40代男性のラジオDJのように、"
                    "落ち着いてゆっくり語りかけるように読んでください。"
                    "急がず、一文一文丁寧に間を取って。\n\n"
                ),
            },
            "sub": {
                "voice_name": "Zephyr",
                "prompt_prefix": (
                    "以下のセリフを、明るく好奇心旺盛な20代男性として、"
                    "元気にテンポよく読んでください。"
                    "ただし早口にならず聴き取りやすい速度で。\n\n"
                ),
            },
        }

        out_dir = self._ensure_output_dir(settings.TTS_OUTPUT_DIR)
        ts = int(time.time() * 1000)

        if title:
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:40].strip()
            final_path = out_dir / f"{safe_title}_{ts}.mp3"
        else:
            final_path = out_dir / f"podcast_{ts}.mp3"

        temp_mp3_paths: list[Path] = []

        try:
            for i, (role, text) in enumerate(batched):
                vc = voice_config[role]
                seg_path = out_dir / f"_seg_{ts}_{i:04d}.mp3"

                await self._gemini_tts_to_mp3(
                    text=text,
                    voice_name=vc["voice_name"],
                    prompt_prefix=vc["prompt_prefix"],
                    output_path=seg_path,
                )
                temp_mp3_paths.append(seg_path)

                logger.info(
                    "voice_engine.segment_done",
                    part=i + 1,
                    total=len(batched),
                    role=role,
                )

                # レート制限防止
                if i < len(batched) - 1:
                    await asyncio.sleep(2)

            # --- Step 4: 無音を挟んで結合 ---
            silence_path = out_dir / f"_seg_{ts}_silence.mp3"
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y",
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", "0.3", "-b:a", "256k",
                    str(silence_path),
                ],
                capture_output=True,
            )

            # concat リスト作成
            concat_list_path = out_dir / f"_gemchunk_{ts}_concat.txt"
            concat_lines: list[str] = []
            for j, mp3_path in enumerate(temp_paths):
                concat_lines.append(f"file '{mp3_path.resolve().as_posix()}'")
                if j < len(temp_paths) - 1:
                    concat_lines.append(f"file '{silence_path.resolve().as_posix()}'")
            concat_list_path.write_text("\n".join(concat_lines), encoding="utf-8")

            # 結合（loudnormなし — 各パートで既に適用済み）
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_path),
                    "-c", "copy",
                    str(final_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                logger.error("voice_engine.ffmpeg_concat_failed", error=error_msg[-500:], concat_list=str(concat_list_path))
                raise RuntimeError(f"ffmpeg concat failed: {error_msg[-500:]}")

        finally:
            for p in temp_paths:
                p.unlink(missing_ok=True)
            silence_path.unlink(missing_ok=True) if 'silence_path' in dir() else None
            concat_list_path.unlink(missing_ok=True) if 'concat_list_path' in dir() else None

        logger.info(
            "voice_engine.gemini_chunked.done",
            path=str(final_path),
            chunks=len(chunks),
        )
        return final_path

    @staticmethod
    def _split_script_at_dialogue(script: str, max_chars: int) -> list[str]:
        """台本を対話の区切り（山口:/田中:）で分割する."""
        lines = script.split("\n")
        chunks: list[str] = []
        current_chunk: list[str] = []
        current_len = 0

        for line in lines:
            line_len = len(line) + 1  # +1 for newline
            # チャンクサイズ超過 & 話者ラベルの行で分割
            if (current_len + line_len > max_chars
                    and current_len > 0
                    and (line.startswith("山口:") or line.startswith("山口：")
                         or line.startswith("田中:") or line.startswith("田中："))):
                chunks.append("\n".join(current_chunk))
                current_chunk = []
                current_len = 0
            current_chunk.append(line)
            current_len += line_len

        if current_chunk:
            chunks.append("\n".join(current_chunk))

        return chunks

    async def _synthesize_gemini_single(
        self, script: str, language: str, title: str = "",
    ) -> Path:
        """Gemini TTS で短い台本を1リクエストで合成する.

        1500文字以内の台本をEnceladusボイスで一括読み上げ。
        山口と田中の演じ分けはプロンプトで指示。
        """
        logger.info(
            "voice_engine.gemini_single.start",
            language=language,
            script_length=len(script),
        )

        # --- 出力パス ---
        out_dir = self._ensure_output_dir(settings.TTS_OUTPUT_DIR)
        ts = int(time.time() * 1000)
        if title:
            safe_title = re.sub(r'[\\/*?:"<>|]', '', title)[:40].strip()
            final_filename = f"{safe_title}_{ts}.mp3"
        else:
            final_filename = f"podcast_{ts}.mp3"
        final_path = out_dir / final_filename

        # --- TTS プロンプト ---
        tts_prompt = (
            "以下のポッドキャスト台本を自然に読み上げてください。\n"
            "【重要】全体的にゆっくりめのペースで話してください。急がず、一文一文丁寧に。\n"
            "2人の登場人物がいます。はっきり声を変えて演じ分けてください。\n"
            "山口：40代男性。低く太い声で、特にゆっくり落ち着いて話す。渋みのあるトーン。文と文の間に十分な間を取る。\n"
            "田中：20代男性。明るく高めの声で、やや元気に話す。ただし早口にならず聴き取りやすい速度で。\n"
            "「山口:」「田中:」のラベルは読み上げず、声の高さ・テンポ・トーンで2人を明確に区別してください。\n"
            "会話の間を多めに取り、リラックスして聴けるテンポで読んでください。\n\n"
            + script
        )

        # --- Gemini TTS 1リクエスト（リトライ付き） ---
        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        wav_path = out_dir / f"_gemtts_{ts}_full.wav"
        _TTS_MAX_RETRIES = 3

        try:
            def _tts_full() -> None:
                for _retry in range(_TTS_MAX_RETRIES):
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
                        if (
                            not response.candidates
                            or not response.candidates[0].content
                            or not response.candidates[0].content.parts
                        ):
                            if _retry < _TTS_MAX_RETRIES - 1:
                                import time as _time
                                _time.sleep(5)
                                continue
                            raise RuntimeError("Gemini TTS returned empty response")
                        audio_data = response.candidates[0].content.parts[0].inline_data.data
                        data_size = len(audio_data)
                        header = struct.pack(
                            '<4sI4s4sIHHIIHH4sI',
                            b'RIFF', 36 + data_size, b'WAVE',
                            b'fmt ', 16, 1, 1, 24000, 24000 * 2, 2, 16,
                            b'data', data_size,
                        )
                        wav_path.write_bytes(header + audio_data)
                        return
                    except RuntimeError:
                        raise
                    except Exception as e:
                        if _retry < _TTS_MAX_RETRIES - 1:
                            import time as _time
                            _time.sleep(5)
                            continue
                        raise

            # 300秒タイムアウト付きで実行（リトライ含むため延長）
            await asyncio.wait_for(asyncio.to_thread(_tts_full), timeout=300)

            # --- ffmpeg: WAV → MP3 (loudnorm + highpass + lowpass + atempo) ---
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-af", "aresample=resampler=soxr,highpass=f=50,lowpass=f=15000,loudnorm=I=-16:TP=-3:LRA=13,atempo=1.0",
                    "-ar", "48000", "-b:a", "256k",
                    str(final_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"ffmpeg failed: {error_msg[:300]}")

        finally:
            wav_path.unlink(missing_ok=True)

        logger.info(
            "voice_engine.gemini_single.done",
            path=str(final_path),
            size=final_path.stat().st_size if final_path.exists() else 0,
        )
        return final_path

    async def _synthesize_gemini_dialogue(
        self, script: str, language: str, title: str = "",
    ) -> Path:
        """Gemini TTS で対話形式の台本を2ボイスで合成する.

        山口 → Enceladus（低め渋い40代男性DJ）、
        田中 → Zephyr（明るく好奇心旺盛な若い男性）で
        各セリフを個別に合成し、loudnorm + silence挿入 + atempo で仕上げる。
        """
        # --- 台本をセリフ単位にパース ---
        segments: list[tuple[str, str]] = []  # (role, text)
        for line in script.split("\n"):
            line = line.strip()
            if not line:
                continue
            if line.startswith("山口:") or line.startswith("山口："):
                text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if text:
                    segments.append(("host", text))
            elif line.startswith("田中:") or line.startswith("田中："):
                text = line.split(":", 1)[-1].split("：", 1)[-1].strip()
                if text:
                    segments.append(("assistant", text))
            else:
                # ラベルなし行は直前の話者を継続、なければ山口
                role = segments[-1][0] if segments else "host"
                segments.append((role, line))

        if not segments:
            logger.warning("voice_engine.gemini_dialogue.no_lines")
            segments = [("host", script)]

        # --- 同一話者の連続セリフをバッチ化（リクエスト数削減） ---
        batched: list[tuple[str, str]] = []
        for role, text in segments:
            if batched and batched[-1][0] == role:
                batched[-1] = (role, batched[-1][1] + "\n" + text)
            else:
                batched.append((role, text))

        # --- 話者ごとにボイスを使い分け（山口=Enceladus, 田中=Zephyr） ---
        # 同一話者の連続セリフはバッチ化済み。各バッチを話者のボイスで合成。
        segments = batched

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

        # --- 話者ごとのボイス・プロンプト設定 ---
        voice_config = {
            "host": {
                "voice_name": "Enceladus",
                "prompt_prefix": "以下のセリフを、低めで渋い40代男性のラジオDJのように、落ち着いてゆっくり語りかけるように読んでください。急がず、一文一文丁寧に間を取って。\n\n",
            },
            "assistant": {
                "voice_name": "Zephyr",
                "prompt_prefix": "以下のセリフを、明るく好奇心旺盛な20代男性として、元気にテンポよく読んでください。ただし早口にならず聴き取りやすい速度で。\n\n",
            },
        }

        client = genai.Client(api_key=settings.GEMINI_API_KEY)
        temp_wav_paths: list[Path] = []
        temp_mp3_paths: list[Path] = []

        try:
            # --- 各セグメントを話者ごとのボイスでTTS合成 ---
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

                # リトライ付きTTS呼び出し（空レスポンス対策）
                max_retries = 3
                for attempt in range(max_retries):
                    try:
                        await asyncio.to_thread(
                            _tts_segment, tts_prompt, vc["voice_name"], wav_path,
                        )
                        break
                    except RuntimeError as e:
                        if attempt < max_retries - 1:
                            logger.warning(
                                "voice_engine.gemini_dialogue.retry",
                                segment=i, attempt=attempt + 1, error=str(e),
                            )
                            await asyncio.sleep(3)
                        else:
                            raise

                temp_wav_paths.append(wav_path)

                logger.debug(
                    "voice_engine.gemini_dialogue.segment_done",
                    segment=i,
                    role=role,
                )

                # レート制限防止: セグメント間に2秒待機
                if i < len(segments) - 1:
                    await asyncio.sleep(2)

            # --- ffmpeg: 各WAVセグメントをMP3に変換（loudnorm + フィルタ） ---
            for wav_path in temp_wav_paths:
                mp3_path = wav_path.with_suffix(".mp3")
                result = await asyncio.to_thread(
                    subprocess.run,
                    [
                        "ffmpeg", "-y", "-i", str(wav_path),
                        "-af", "highpass=f=50,lowpass=f=15000",
                        "-ar", "48000", "-b:a", "256k",
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
                    "-f", "lavfi", "-i", "anullsrc=r=48000:cl=mono",
                    "-t", "0.3", "-b:a", "256k",
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

            # 結合 + loudnorm
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y", "-f", "concat", "-safe", "0",
                    "-i", str(concat_list_path),
                    "-af", "loudnorm=I=-16:TP=-3:LRA=13",
                    "-b:a", "256k", "-ar", "48000",
                    str(final_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"ffmpeg concat failed: {error_msg[:300]}")

        finally:
            # 一時ファイル削除
            for p in temp_mp3_paths:
                p.unlink(missing_ok=True)
            silence_path = out_dir / f"_seg_{ts}_silence.mp3"
            silence_path.unlink(missing_ok=True)
            concat_list_path = out_dir / f"_seg_{ts}_concat.txt"
            concat_list_path.unlink(missing_ok=True)

        # --- Step 5: 音声生成完了（バリデーションは呼び出し元のsynthesize_podcastで実施） ---
        duration_sec = await self._get_audio_duration(final_path)
        logger.info(
            "voice_engine.synthesize_podcast.done",
            path=str(final_path),
            segments=len(batched),
            duration=duration_sec,
        )
        return final_path

    async def list_available_voices(
        self, backend: Any = None,
    ) -> dict[str, Any]:
        """利用可能なボイス一覧を返す."""
        return {
            "gemini_tts": {
                "voices": [
                    {"name": "Enceladus", "role": "host/山口", "quality": "very_high"},
                    {"name": "Zephyr", "role": "sub/田中", "quality": "very_high"},
                ],
                "note": "Gemini 2.5 Flash TTS. Two voices for 3-minute dual-host podcast.",
            },
        }

    async def check_backends(self) -> dict[str, bool]:
        """TTS バックエンドの可用性をチェックする."""
        try:
            client = genai.Client(api_key=settings.GEMINI_API_KEY)
            # 簡単なテストでAPIキー有効性を確認
            return {"gemini_tts": bool(settings.GEMINI_API_KEY)}
        except Exception:
            return {"gemini_tts": False}

    # ------------------------------------------------------------------
    # Audio duration check
    # ------------------------------------------------------------------

    @staticmethod
    async def _get_audio_duration(path: Path) -> float | None:
        """ffprobeで音声ファイルの長さ（秒）を取得する."""
        try:
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffprobe", "-v", "quiet",
                    "-show_entries", "format=duration",
                    "-of", "csv=p=0",
                    str(path),
                ],
                capture_output=True,
                text=True,
            )
            if result.returncode == 0 and result.stdout.strip():
                return float(result.stdout.strip())
        except Exception as exc:
            logger.warning("voice_engine.duration_check_failed", error=str(exc))
        return None

    # ------------------------------------------------------------------
    # Gemini TTS core
    # ------------------------------------------------------------------

    async def _gemini_tts_to_mp3(
        self,
        text: str,
        voice_name: str,
        prompt_prefix: str,
        output_path: Path,
    ) -> None:
        """Gemini TTS でテキストを合成し、MP3で出力する.

        Args:
            text: 読み上げるテキスト.
            voice_name: Gemini TTSのボイス名 (Enceladus/Zephyr等).
            prompt_prefix: TTS プロンプトの前置き.
            output_path: 出力MP3パス.
        """
        out_dir = output_path.parent
        ts = int(time.time() * 1000)
        wav_path = out_dir / f"_tts_{ts}_{output_path.stem}.wav"

        tts_prompt = prompt_prefix + text
        client = genai.Client(api_key=settings.GEMINI_API_KEY)

        try:
            def _tts() -> None:
                # リトライ付き
                max_retries = 3
                last_exc = None
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
                                            voice_name=voice_name,
                                        )
                                    )
                                ),
                            ),
                        )
                        if (
                            not response.candidates
                            or not response.candidates[0].content
                            or not response.candidates[0].content.parts
                        ):
                            raise RuntimeError("Gemini TTS returned empty response")

                        audio_data = response.candidates[0].content.parts[0].inline_data.data
                        data_size = len(audio_data)
                        header = struct.pack(
                            '<4sI4s4sIHHIIHH4sI',
                            b'RIFF', 36 + data_size, b'WAVE',
                            b'fmt ', 16, 1, 1, 24000, 24000 * 2, 2, 16,
                            b'data', data_size,
                        )
                        wav_path.write_bytes(header + audio_data)
                        return
                    except Exception as e:
                        last_exc = e
                        if attempt < max_retries - 1:
                            import time as t
                            t.sleep(3)
                if last_exc:
                    raise last_exc

            # 180秒タイムアウト
            await asyncio.wait_for(asyncio.to_thread(_tts), timeout=180)

            # WAV → MP3 (loudnorm + フィルタ)
            result = await asyncio.to_thread(
                subprocess.run,
                [
                    "ffmpeg", "-y", "-i", str(wav_path),
                    "-af", "aresample=resampler=soxr,highpass=f=50,lowpass=f=15000,loudnorm=I=-16:TP=-3:LRA=13",
                    "-ar", "48000", "-b:a", "256k",
                    str(output_path),
                ],
                capture_output=True,
            )
            if result.returncode != 0:
                error_msg = result.stderr.decode("utf-8", errors="replace")
                raise RuntimeError(f"ffmpeg failed: {error_msg[:300]}")

        finally:
            wav_path.unlink(missing_ok=True)

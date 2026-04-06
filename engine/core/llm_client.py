"""Deepcast Engine — Gemini Flash LLM クライアント (Singleton).

Google Gemini Flash API と非同期で通信するシングルトンクライアント。
リトライ・タイムアウト・エラーハンドリングを備える。
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import structlog
from google import genai

from config.settings import settings

logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Retry
# ---------------------------------------------------------------------------
_MAX_RETRIES: int = 3
_BACKOFF_BASE: float = 1.0  # exponential backoff base (seconds)


class LLMClient:
    """Gemini Flash API と通信するシングルトン非同期クライアント.

    Usage::

        client = LLMClient()
        text = await client.generate("Hello", system_prompt="You are helpful.")
    """

    _instance: LLMClient | None = None
    _lock: threading.Lock = threading.Lock()

    # ------------------------------------------------------------------
    # Singleton
    # ------------------------------------------------------------------

    def __new__(cls) -> LLMClient:
        """スレッドセーフなシングルトンを返す."""
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    instance = super().__new__(cls)
                    instance._initialized = False
                    cls._instance = instance
        return cls._instance

    def __init__(self) -> None:
        if self._initialized:
            return
        self._client = genai.Client(api_key=settings.GEMINI_API_KEY)
        self._model = "gemini-2.5-flash"
        self._initialized = True
        logger.info(
            "llm_client.initialized",
            backend="gemini_flash",
            model=self._model,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def generate(
        self,
        prompt: str,
        system_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.7,
        max_tokens: int = 8192,
    ) -> str:
        """テキスト生成を実行する.

        Args:
            prompt: ユーザープロンプト.
            system_prompt: システムプロンプト.
            model: 使用モデル名 (省略時はデフォルト).
            temperature: 生成温度 (0.0 - 1.0).
            max_tokens: 最大トークン数.

        Returns:
            生成されたテキスト.
        """
        use_model = model or self._model
        full_prompt = f"{system_prompt}\n\n{prompt}" if system_prompt else prompt

        logger.debug(
            "llm_client.generate.request",
            model=use_model,
            prompt_length=len(prompt),
            temperature=temperature,
        )

        last_exc: Exception | None = None
        for attempt in range(1, _MAX_RETRIES + 1):
            try:
                def _call():
                    response = self._client.models.generate_content(
                        model=use_model,
                        contents=full_prompt,
                        config=genai.types.GenerateContentConfig(
                            temperature=temperature,
                            max_output_tokens=max_tokens,
                        ),
                    )
                    return response.text

                text = await asyncio.wait_for(
                    asyncio.to_thread(_call), timeout=120
                )

                logger.info(
                    "llm_client.generate.done",
                    model=use_model,
                    response_length=len(text) if text else 0,
                )
                return text or ""

            except Exception as exc:
                last_exc = exc
                logger.warning(
                    "llm_client.generate.retry",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * (2 ** (attempt - 1)))

        raise last_exc or RuntimeError("generate failed after retries")

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """JSON 形式でテキスト生成し、dict を返す.

        Args:
            prompt: ユーザープロンプト.
            system_prompt: システムプロンプト.
            model: 使用モデル名 (省略時はデフォルト).
            temperature: 生成温度.

        Returns:
            パース済みの dict.
        """
        json_prompt = (
            f"{system_prompt}\n\n{prompt}\n\n"
            "IMPORTANT: Return ONLY valid JSON. No markdown fences, no extra text."
        )

        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            logger.debug(
                "llm_client.generate_json.request",
                attempt=attempt,
            )

            try:
                raw_text = await self.generate(
                    prompt=prompt,
                    system_prompt=system_prompt + "\n\nIMPORTANT: Return ONLY valid JSON. No markdown fences, no extra text.",
                    temperature=temperature,
                    max_tokens=8192,
                )

                # マークダウンコードフェンスを除去
                text = raw_text.strip()
                if text.startswith("```"):
                    text = text.split("\n", 1)[1] if "\n" in text else text[3:]
                    if text.endswith("```"):
                        text = text[:text.rfind("```")]
                    text = text.strip()

                parsed = json.loads(text)

                if not isinstance(parsed, dict):
                    last_error = TypeError(f"Expected dict, got {type(parsed).__name__}")
                    if attempt < _MAX_RETRIES:
                        await asyncio.sleep(_BACKOFF_BASE * attempt)
                    continue

                logger.info(
                    "llm_client.generate_json.done",
                    keys=list(parsed.keys()),
                )
                return parsed

            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(
                    "llm_client.generate_json.parse_failed",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * attempt)

            except Exception as exc:
                last_error = exc
                logger.warning(
                    "llm_client.generate_json.error",
                    attempt=attempt,
                    error=str(exc),
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * attempt)

        msg = f"Failed to obtain valid JSON dict after {_MAX_RETRIES} attempts"
        logger.error("llm_client.generate_json.exhausted", last_error=str(last_error))
        raise ValueError(msg) from last_error

    async def check_health(self) -> bool:
        """Gemini API の稼働状態を確認する."""
        try:
            def _check():
                response = self._client.models.generate_content(
                    model=self._model,
                    contents="Say OK",
                    config=genai.types.GenerateContentConfig(
                        max_output_tokens=10,
                    ),
                )
                return bool(response.text)

            result = await asyncio.wait_for(asyncio.to_thread(_check), timeout=10)
            logger.debug("llm_client.health", healthy=result)
            return result
        except Exception as exc:
            logger.warning("llm_client.health.unreachable", error=str(exc))
            return False

    async def list_models(self) -> list[str]:
        """利用可能なモデル一覧を返す."""
        return [self._model]

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """クリーンアップ（Geminiクライアントは明示的なclose不要）."""
        logger.info("llm_client.closed")

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

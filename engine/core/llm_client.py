"""Deepcast Engine — Ollama LLM クライアント (Singleton).

Ollama REST API と非同期で通信するシングルトンクライアント。
httpx.AsyncClient を使用し、リトライ・タイムアウト・エラーハンドリングを備える。
"""

from __future__ import annotations

import asyncio
import json
import threading
from typing import Any

import httpx
import structlog

from config.settings import settings
logger = structlog.get_logger(__name__)

# ---------------------------------------------------------------------------
# Timeout constants (seconds)
# ---------------------------------------------------------------------------
_TIMEOUT_DEFAULT: float = 300.0
_TIMEOUT_LONG: float = 600.0
_HEALTH_TIMEOUT: float = 10.0

# Retry
_MAX_RETRIES: int = 3
_BACKOFF_BASE: float = 1.0  # exponential backoff base (seconds)


class LLMClient:
    """Ollama API と通信するシングルトン非同期クライアント.

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
        self._base_url: str = settings.OLLAMA_BASE_URL.rstrip("/")
        self._default_model: str = settings.OLLAMA_MODEL_GENERATE
        self._client: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(_TIMEOUT_DEFAULT, connect=10.0),
        )
        self._initialized = True
        logger.info(
            "llm_client.initialized",
            base_url=self._base_url,
            default_model=self._default_model,
        )

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _request_with_retry(
        self,
        method: str,
        path: str,
        *,
        json_body: dict[str, Any] | None = None,
        timeout: float = _TIMEOUT_DEFAULT,
        max_retries: int = _MAX_RETRIES,
    ) -> httpx.Response:
        """指数バックオフ付きの HTTP リクエスト.

        Args:
            method: HTTP メソッド ("GET" / "POST").
            path: エンドポイントパス (例: "/api/generate").
            json_body: POST ボディ (JSON).
            timeout: リクエストタイムアウト (秒).
            max_retries: 最大リトライ回数.

        Returns:
            httpx.Response

        Raises:
            httpx.HTTPStatusError: 4xx/5xx レスポンス (リトライ上限超過後).
            httpx.ConnectError: 接続不可 (リトライ上限超過後).
            httpx.TimeoutException: タイムアウト (リトライ上限超過後).
        """
        last_exc: Exception | None = None

        for attempt in range(1, max_retries + 1):
            try:
                response = await self._client.request(
                    method,
                    path,
                    json=json_body,
                    timeout=timeout,
                )
                response.raise_for_status()
                return response

            except (httpx.ConnectError, httpx.TimeoutException) as exc:
                last_exc = exc
                wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                logger.warning(
                    "llm_client.request_retry",
                    path=path,
                    attempt=attempt,
                    max_retries=max_retries,
                    wait_seconds=wait,
                    error=str(exc),
                )
                if attempt < max_retries:
                    await asyncio.sleep(wait)

            except httpx.HTTPStatusError as exc:
                last_exc = exc
                # 5xx はリトライ、4xx は即時失敗
                if exc.response.status_code >= 500:
                    wait = _BACKOFF_BASE * (2 ** (attempt - 1))
                    logger.warning(
                        "llm_client.server_error_retry",
                        path=path,
                        status=exc.response.status_code,
                        attempt=attempt,
                        wait_seconds=wait,
                    )
                    if attempt < max_retries:
                        await asyncio.sleep(wait)
                else:
                    raise

        # All retries exhausted
        logger.error(
            "llm_client.request_failed",
            path=path,
            retries_exhausted=max_retries,
        )
        if last_exc is None:
            last_exc = RuntimeError(
                f"Request to {path} failed after {max_retries} retries (no exception captured)"
            )
        raise last_exc

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
        max_tokens: int = 4096,
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

        Raises:
            httpx.ConnectError: Ollama に接続できない場合.
            httpx.TimeoutException: タイムアウト時.
        """
        model = model or self._default_model
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        logger.debug(
            "llm_client.generate.request",
            model=model,
            prompt_length=len(prompt),
            temperature=temperature,
            max_tokens=max_tokens,
        )

        response = await self._request_with_retry(
            "POST",
            "/api/generate",
            json_body=payload,
            timeout=_TIMEOUT_LONG,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(
                f"generate: Ollama returned non-JSON response "
                f"(status={response.status_code}, body={response.text[:200]!r})"
            ) from exc
        text: str = data.get("response", "")

        logger.info(
            "llm_client.generate.done",
            model=model,
            response_length=len(text),
        )
        return text

    async def generate_json(
        self,
        prompt: str,
        system_prompt: str,
        *,
        model: str | None = None,
        temperature: float = 0.3,
    ) -> dict[str, Any]:
        """JSON 形式でテキスト生成し、dict を返す.

        Ollama の ``format="json"`` パラメータを使用する。
        JSON パースに失敗した場合は最大 3 回リトライする。

        Args:
            prompt: ユーザープロンプト.
            system_prompt: システムプロンプト.
            model: 使用モデル名 (省略時はデフォルト).
            temperature: 生成温度 (デフォルト 0.3: JSON 出力は低めが安定).

        Returns:
            パース済みの dict.

        Raises:
            ValueError: 3 回リトライしても有効な JSON dict が得られなかった場合.
        """
        model = model or self._default_model
        payload: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "system": system_prompt,
            "stream": False,
            "format": "json",
            "options": {
                "temperature": temperature,
            },
        }

        last_error: Exception | None = None

        for attempt in range(1, _MAX_RETRIES + 1):
            logger.debug(
                "llm_client.generate_json.request",
                model=model,
                attempt=attempt,
            )

            response = await self._request_with_retry(
                "POST",
                "/api/generate",
                json_body=payload,
                timeout=_TIMEOUT_LONG,
            )
            try:
                resp_data = response.json()
            except ValueError as exc:
                last_error = exc
                logger.warning(
                    "llm_client.generate_json.response_not_json",
                    attempt=attempt,
                    error=str(exc),
                    body=response.text[:200],
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * attempt)
                continue
            raw_text: str = resp_data.get("response", "")

            try:
                parsed = json.loads(raw_text)
            except json.JSONDecodeError as exc:
                last_error = exc
                logger.warning(
                    "llm_client.generate_json.parse_failed",
                    attempt=attempt,
                    error=str(exc),
                    raw_text=raw_text[:200],
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * attempt)
                continue

            if not isinstance(parsed, dict):
                last_error = TypeError(
                    f"Expected dict, got {type(parsed).__name__}"
                )
                logger.warning(
                    "llm_client.generate_json.not_dict",
                    attempt=attempt,
                    actual_type=type(parsed).__name__,
                )
                if attempt < _MAX_RETRIES:
                    await asyncio.sleep(_BACKOFF_BASE * attempt)
                continue

            logger.info(
                "llm_client.generate_json.done",
                model=model,
                keys=list(parsed.keys()),
            )
            return parsed

        msg = f"Failed to obtain valid JSON dict after {_MAX_RETRIES} attempts"
        logger.error("llm_client.generate_json.exhausted", last_error=str(last_error))
        raise ValueError(msg) from last_error

    async def check_health(self) -> bool:
        """Ollama サーバーの稼働状態を確認する.

        Returns:
            True: 正常稼働中, False: 応答なし / エラー.
        """
        try:
            response = await self._client.get(
                "/api/tags",
                timeout=_HEALTH_TIMEOUT,
            )
            healthy = response.status_code == 200
            logger.debug("llm_client.health", healthy=healthy)
            return healthy
        except (httpx.ConnectError, httpx.TimeoutException) as exc:
            logger.warning("llm_client.health.unreachable", error=str(exc))
            return False

    async def list_models(self) -> list[str]:
        """Ollama にインストール済みのモデル名一覧を返す.

        Returns:
            モデル名のリスト (例: ``["llama3:latest", "gemma2:latest"]``).

        Raises:
            httpx.ConnectError: Ollama に接続できない場合.
        """
        response = await self._request_with_retry(
            "GET",
            "/api/tags",
            timeout=_HEALTH_TIMEOUT,
            max_retries=2,
        )
        try:
            data = response.json()
        except ValueError as exc:
            raise ValueError(
                f"list_models: Ollama returned non-JSON response "
                f"(status={response.status_code}, body={response.text[:200]!r})"
            ) from exc
        models: list[str] = [
            m["name"] for m in data.get("models", [])
        ]
        logger.info("llm_client.list_models", count=len(models), models=models)
        return models

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def close(self) -> None:
        """内部 httpx クライアントを閉じる."""
        await self._client.aclose()
        logger.info("llm_client.closed")

    async def __aenter__(self) -> LLMClient:
        return self

    async def __aexit__(self, *exc: Any) -> None:
        await self.close()

from __future__ import annotations

import os
import unittest
from asyncio import run
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import HTTPException

from app.api.v1.speech import transcribe_audio
from app.core.config import Settings, clear_settings_cache


class FakeAsyncClient:
    def __init__(
        self,
        *,
        responses: list[httpx.Response] | None = None,
        raised_exception: Exception | None = None,
        requests: list[httpx.Request] | None = None,
    ) -> None:
        self._responses = responses or []
        self._raised_exception = raised_exception
        self._requests = requests if requests is not None else []
        self._index = 0

    async def __aenter__(self) -> FakeAsyncClient:
        return self

    async def __aexit__(self, exc_type, exc, tb) -> bool:
        return False

    async def post(
        self,
        url: str,
        *,
        headers: dict[str, str] | None = None,
        content: bytes | None = None,
    ) -> httpx.Response:
        request = httpx.Request("POST", url, headers=headers, content=content)
        self._requests.append(request)
        if self._raised_exception is not None:
            raise self._raised_exception

        response = self._responses[min(self._index, len(self._responses) - 1)]
        self._index += 1
        return httpx.Response(
            response.status_code,
            headers=response.headers,
            content=response.content,
            request=request,
        )


class FakeUploadFile:
    def __init__(self, *, content: bytes, content_type: str) -> None:
        self._content = content
        self.content_type = content_type

    async def read(self) -> bytes:
        return self._content


class SpeechEndpointTests(unittest.TestCase):
    def setUp(self) -> None:
        self.env = dict(os.environ)
        self.env.update(
            {
                "APP_ENV": "test",
                "HOST": "127.0.0.1",
                "PORT": "8100",
                "DATA_SERVICE_BASE_URL": "http://data-service.local",
                "GEMINI_API_KEY": "gemini-test-key",
                "GOOGLE_MAPS_API_KEY": "gmaps-key",
                "CORS_ALLOW_ORIGINS": "http://localhost:5173",
                "LOG_LEVEL": "INFO",
                "HF_API_KEY": "hf-test-key",
                "HF_ENDPOINT_URL": "https://speech.example.endpoints.huggingface.cloud",
            }
        )
        clear_settings_cache()

    def tearDown(self) -> None:
        clear_settings_cache()

    def _build_request(self):
        with patch.dict(os.environ, self.env, clear=True):
            settings = Settings()
        return SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(settings=settings)))

    @staticmethod
    def _build_upload_file() -> FakeUploadFile:
        return FakeUploadFile(content=b"fake-audio", content_type="audio/webm")

    def test_transcribe_retries_retryable_upstream_error(self) -> None:
        request = self._build_request()
        file = self._build_upload_file()
        requests: list[httpx.Request] = []
        responses = [
            httpx.Response(503, json={"error": "Model is loading"}),
            httpx.Response(200, json={"text": "台語測試"}),
        ]

        with patch("app.api.v1.speech._to_wav", new=AsyncMock(return_value=b"wav-bytes")):
            with patch("app.api.v1.speech.asyncio.sleep", new=AsyncMock()) as sleep_mock:
                with patch(
                    "app.api.v1.speech.httpx.AsyncClient",
                    new=lambda *args, **kwargs: FakeAsyncClient(
                        responses=responses,
                        requests=requests,
                    ),
                ):
                    response = run(transcribe_audio(request, file))

        self.assertEqual(response, {"text": "台語測試"})
        self.assertEqual(len(requests), 2)
        self.assertEqual(requests[0].headers["x-wait-for-model"], "true")
        sleep_mock.assert_awaited_once_with(1.0)

    def test_transcribe_returns_503_when_upstream_never_recovers(self) -> None:
        request = self._build_request()
        file = self._build_upload_file()
        responses = [httpx.Response(503, json={"error": "Model is loading"})]

        with patch("app.api.v1.speech._to_wav", new=AsyncMock(return_value=b"wav-bytes")):
            with patch("app.api.v1.speech.asyncio.sleep", new=AsyncMock()):
                with patch(
                    "app.api.v1.speech.httpx.AsyncClient",
                    new=lambda *args, **kwargs: FakeAsyncClient(
                        responses=responses,
                    ),
                ):
                    with self.assertRaises(HTTPException) as ctx:
                        run(transcribe_audio(request, file))

        self.assertEqual(ctx.exception.status_code, 503)
        self.assertEqual(ctx.exception.detail, "語音辨識模型啟動中，請稍後再試一次。")

    def test_transcribe_returns_504_on_upstream_timeout(self) -> None:
        request = self._build_request()
        file = self._build_upload_file()
        http_request = httpx.Request("POST", "https://speech.example.endpoints.huggingface.cloud")

        with patch("app.api.v1.speech._to_wav", new=AsyncMock(return_value=b"wav-bytes")):
            with patch(
                "app.api.v1.speech.httpx.AsyncClient",
                new=lambda *args, **kwargs: FakeAsyncClient(
                    raised_exception=httpx.ReadTimeout("timed out", request=http_request),
                ),
            ):
                with self.assertRaises(HTTPException) as ctx:
                    run(transcribe_audio(request, file))

        self.assertEqual(ctx.exception.status_code, 504)
        self.assertEqual(ctx.exception.detail, "語音辨識服務逾時，請稍後再試一次。")

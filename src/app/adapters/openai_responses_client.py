from __future__ import annotations

import base64
import json
import os
from pathlib import Path
from typing import Any, Sequence

from openai import APIConnectionError, APIError, OpenAI, RateLimitError

from llama_index.core.schema import ImageDocument


class OpenAIResponsesResult:
    """Simple response object that mirrors the interface used by parsing adapter."""

    def __init__(self, text: str) -> None:
        self.text = text


class OpenAIResponsesClient:
    """Thin wrapper around the OpenAI Responses API that supports multi-modal inputs."""

    def __init__(
        self,
        *,
        model: str,
        api_key: str | None = None,
        timeout: float = 60.0,
    ) -> None:
        self._model = model
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._timeout = timeout

    def complete(
        self,
        prompt: str,
        *,
        image_documents: Sequence[ImageDocument] | None = None,
        schema: dict[str, Any] | None = None,
    ) -> OpenAIResponsesResult:
        content: list[dict[str, Any]] = [{"type": "input_text", "text": prompt}]
        content.extend(self._build_image_entries(image_documents or []))

        if schema:
            schema_instruction = (
                "\nRespond ONLY with JSON that matches this schema:\n"
                f"{json.dumps(schema)}\n"
            )
            content[0]["text"] = f"{prompt}{schema_instruction}"

        response_kwargs: dict[str, Any] = {
            "model": self._model,
            "input": [
                {
                    "role": "user",
                    "content": content,
                }
            ],
            "timeout": self._timeout,
        }

        try:
            response = self._client.responses.create(**response_kwargs)
        except (APIConnectionError, APIError, RateLimitError) as exc:
            raise RuntimeError(f"OpenAI responses API error: {exc}") from exc

        text = self._extract_text(response)
        return OpenAIResponsesResult(text=text)

    def _build_image_entries(self, docs: Sequence[ImageDocument]) -> list[dict[str, Any]]:
        entries: list[dict[str, Any]] = []
        for doc in docs:
            data_url = self._resolve_image_url(doc)
            if data_url:
                entries.append(
                    {
                        "type": "input_image",
                        "image_url": data_url,
                    }
                )
        return entries

    def _resolve_image_url(self, document: ImageDocument) -> str | None:
        mimetype = document.image_mimetype or "image/png"
        if document.image:
            return f"data:{mimetype};base64,{document.image}"
        if document.image_path:
            return self._encode_path(document.image_path, mimetype)
        file_path = document.metadata.get("file_path")
        if file_path:
            return self._encode_path(str(file_path), mimetype)
        return None

    @staticmethod
    def _encode_path(path: str, mimetype: str) -> str:
        data = Path(path).read_bytes()
        encoded = base64.b64encode(data).decode("utf-8")
        return f"data:{mimetype};base64,{encoded}"

    @staticmethod
    def _extract_text(response: Any) -> str:
        chunks: list[str] = []
        for item in getattr(response, "output", []):
            for content in getattr(item, "content", []):
                if getattr(content, "type", "") == "output_text":
                    chunks.append(getattr(content, "text", ""))
        joined = "".join(chunks).strip()
        if not joined:
            joined = getattr(response, "output", repr(response))
        return joined

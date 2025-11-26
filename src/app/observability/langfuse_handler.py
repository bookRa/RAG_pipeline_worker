from __future__ import annotations

import re
from typing import Any, Iterable

from langfuse.client import StatefulGenerationClient
from langfuse.llama_index import LlamaIndexCallbackHandler
from langfuse.llama_index.utils import CallbackEvent
from llama_index.core.callbacks.schema import EventPayload


def _flatten_messages(messages: Iterable[Any]) -> str:
    """Return a concatenated string from a LlamaIndex message payload."""
    chunks: list[str] = []
    for message in messages or []:
        if isinstance(message, dict):
            content = message.get("content")
            if isinstance(content, list):
                for part in content:
                    if isinstance(part, dict) and "text" in part:
                        chunks.append(str(part["text"]))
            elif isinstance(content, str):
                chunks.append(content)
        elif hasattr(message, "content"):
            chunks.append(str(message.content))
    return "\n".join(chunks).strip()


class PipelineLangfuseHandler(LlamaIndexCallbackHandler):
    """Custom Langfuse handler that assigns friendlier names & inputs to generations."""

    PROMPT_LABELS = [
        ("# chunk summary generation", "Chunk Summary LLM", "chunk_summary"),
        ("# document summary generation", "Document Summary LLM", "document_summary"),
        ("you normalize parsed document content", "Cleaning LLM", "cleaning"),
        ("component-aware chunking", "Chunking LLM", "chunking"),
        ("table summarization", "Table Summary LLM", "table_summary"),
    ]

    def _handle_LLM_events(self, event_id: str, parent, trace_id: str) -> StatefulGenerationClient:  # type: ignore[override]
        generation = super()._handle_LLM_events(event_id, parent, trace_id)
        label, prompt, metadata = self._infer_label_and_prompt(event_id)

        updates: dict[str, Any] = {}
        if label:
            updates["name"] = label
        if prompt:
            updates["input"] = prompt
        if metadata:
            updates["metadata"] = {
                **(metadata or {}),
            }

        if updates:
            generation.update(**updates)
        return generation

    def _infer_label_and_prompt(self, event_id: str) -> tuple[str | None, str | None, dict[str, Any] | None]:
        events = self.event_map.get(event_id, [])
        if not events:
            return None, None, None

        start_event = events[0]
        prompt = self._extract_prompt(events)
        normalized_prompt = prompt.lower() if prompt else ""

        label = None
        stage = None
        for needle, candidate_label, stage_name in self.PROMPT_LABELS:
            if needle in normalized_prompt:
                label = candidate_label
                stage = stage_name
                break

        if label is None:
            serialized = (start_event.payload or {}).get(EventPayload.SERIALIZED)
            label = (
                serialized.get("class_name")
                if isinstance(serialized, dict)
                else None
            )

        if label and stage:
            return label, prompt, {"pipeline_stage": stage}
        if label:
            return label, prompt, None
        return None, prompt, None

    def _extract_prompt(self, events: list[CallbackEvent]) -> str | None:
        """Attempt to reconstruct the human-readable prompt text."""
        for event in events:
            payload = event.payload or {}
            prompt = payload.get(EventPayload.PROMPT)
            if isinstance(prompt, str) and prompt.strip():
                return prompt.strip()
            template = payload.get(EventPayload.TEMPLATE)
            if isinstance(template, str) and template.strip():
                return template.strip()
            messages = payload.get(EventPayload.MESSAGES)
            if messages:
                flattened = _flatten_messages(messages)
                if flattened:
                    return flattened
        return None


__all__ = ["PipelineLangfuseHandler"]


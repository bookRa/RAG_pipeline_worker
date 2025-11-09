# LLM Integration Implementation Guide

This guide explains how large language model (LLM) calls plug into the current pipeline, what is already implemented, and how to replace the stub summary adapter with a production-ready integration without breaking the hexagonal architecture.

---

## Current State

- The `SummaryGenerator` port (defined in `src/app/application/interfaces.py`) abstracts “generate a short summary from text.”
- `EnrichmentService` (in `src/app/services/enrichment_service.py`) injects a `SummaryGenerator` instance and calls `summarize()` whenever a chunk lacks a title or summary. It also builds a lightweight document summary from the resulting chunk summaries.
- `LLMSummaryAdapter` (in `src/app/adapters/llm_client.py`) is the default adapter. It simply truncates text and exists as a placeholder until a real LLM client is available.
- `AppContainer` wires the adapter into the service:

```python
self.summary_generator = LLMSummaryAdapter()
self.enrichment_service = EnrichmentService(
    observability=self.observability,
    latency=stage_latency,
    summary_generator=self.summary_generator,
)
```

The rest of the codebase already respects the port, so swapping in a real LLM adapter requires no service changes.

---

## Where LLM Calls Fit

```
Document → … → ChunkingService ─┐
                                ▼
                      EnrichmentService ──▶ SummaryGenerator port ──▶ Adapter (LLM client)
                                                   ▲
                                           Infrastructure boundary
```

- Domain + services never import LLM SDKs directly.
- LLM adapters live under `src/app/adapters/` alongside other infrastructure code.
- Observability events emitted by `EnrichmentService` automatically include chunk counts and document summaries, so swapping adapters immediately surfaces new behavior in the dashboard.

---

## Implementing a Production Summary Adapter

1. **Create a new adapter** under `src/app/adapters/`, e.g., `openai_summary.py`.
2. **Implement the port**:

```python
from __future__ import annotations

import os

from openai import OpenAI  # third-party SDK stays inside the adapter

from ..application.interfaces import SummaryGenerator


class OpenAIChatSummaryAdapter(SummaryGenerator):
    def __init__(self, *, api_key: str | None = None, model: str = "gpt-4o-mini") -> None:
        self._client = OpenAI(api_key=api_key or os.environ.get("OPENAI_API_KEY"))
        self._model = model

    def summarize(self, text: str) -> str:
        if not text:
            return ""
        response = self._client.responses.create(
            model=self._model,
            input=f"Summarize the following chunk in <= 2 sentences:\n\n{text[:4000]}",
            max_output_tokens=120,
        )
        return response.output[0].content[0].text.strip()
```

3. **Wire it in the container** by replacing the stub:

```python
from .adapters.openai_summary import OpenAIChatSummaryAdapter
...
self.summary_generator = OpenAIChatSummaryAdapter()
```

4. **Expose configuration via environment variables** (model name, max tokens, temperature, etc.) so deployments can tune behavior without code changes.
5. **Handle failures gracefully** – catch provider-specific exceptions and fall back to an empty string or a deterministic summary so the pipeline never crashes mid-run.

---

## Testing Strategy

| Test Layer | What to Cover | Notes |
| --- | --- | --- |
| Adapter unit tests | Prompt assembly, error handling, token limits, tracing metadata | Use VCR/cassettes or dependency injection to avoid real API calls in CI. |
| Enrichment service tests | Verify the service calls the injected adapter exactly once per chunk and copies returned summaries into chunk metadata + document summary | `tests/test_services.py` already covers the stub; extend it with adapter fakes to assert behavior. |
| End-to-end tests | Optional smoke tests that mock the adapter to return deterministic text while exercising FastAPI routes/dashboard | Keep them offline; rely on mocks or fixtures. |

Example adapter test skeleton:

```python
class StubClient:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def responses(self, text: str) -> str:
        self.calls.append(text)
        return "summary"


def test_adapter_returns_summary():
    adapter = MySummaryAdapter(client=StubClient())
    assert adapter.summarize("hello world") == "summary"
```

---

## Observability, Cost, and Safeguards

- `EnrichmentService` already emits an `enrichment` event with chunk counts. Extend the `details` payload if the LLM adapter provides confidence scores, token usage, or safety flags.
- Consider caching chunk summaries (e.g., via hashing `chunk.cleaned_text`) before calling an LLM to avoid duplicate spend when rerunning the same document.
- Timeouts and retries belong inside the adapter. Keep them configurable so hosting environments can tune them.
- Sensitive data: if chunks may contain confidential content, ensure the chosen provider and deployment meet compliance requirements. Since adapters live under `src/app/adapters/`, you can create alternate implementations for air-gapped or on-prem models while reusing the same port.

---

## Future Extensions

Once the summary use case is stable, the same pattern can power richer LLM integrations:

- **Chunk metadata enrichment** – Generate keywords, questions, or structured metadata by extending `SummaryGenerator` or adding new ports consumed by `EnrichmentService`.
- **LLM-backed extraction** – Swap or augment `DocumentParser` implementations with LLM-based page interpreters (still respecting the parser port). Keep PDF-to-image conversion and LLM calling inside adapters, never in services.
- **Feedback loops** – Store LLM response metadata (e.g., latency, tokens, finish reasons) inside `chunk.metadata.extra["llm"]` so downstream diagnostics and dashboards can visualize quality metrics.

These enhancements should continue to follow the same architectural rule: define or reuse ports in `application/interfaces.py`, keep adapters in `src/app/adapters/`, and inject them via `container.py`.

---

## Checklist

- [ ] Adapter implements `SummaryGenerator` and handles empty input, timeouts, and provider errors.
- [ ] Secrets (API keys) are loaded from environment variables or secret managers, not hard-coded.
- [ ] `container.py` wires the adapter and exposes configuration knobs.
- [ ] Unit tests cover adapter logic without making live API calls.
- [ ] Service tests confirm `EnrichmentService` copies adapter output into chunk metadata + document summary.
- [ ] Documentation (this guide + `docs/ARCHITECTURE.md` if telemetry changes) updated with the new behavior.
- [ ] `tests/test_architecture.py` still passes (no LLM SDK imports inside services/domain).

---

## References

- `src/app/application/interfaces.py` – `SummaryGenerator` port definition
- `src/app/adapters/llm_client.py` – Current stub (`LLMSummaryAdapter`)
- `src/app/services/enrichment_service.py` – Service that invokes the port
- `src/app/container.py` – Wiring and configuration
- `tests/test_services.py` – Enrichment-oriented tests
- `docs/ARCHITECTURE.md` – Overall dependency flow

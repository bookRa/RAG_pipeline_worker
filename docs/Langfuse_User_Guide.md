# Langfuse Usage Guide

This guide explains how our pipeline emits Langfuse traces and how engineers can use the UI to debug document runs.

## Instrumentation Overview

| Aspect | Details |
| --- | --- |
| Trace name | `document_pipeline::{filename}` |
| Session ID | Pipeline run ID (falls back to document ID) so every stage + LLM call for the same run is grouped together |
| Tags | `["pipeline", "<file_type>"]` |
| Metadata | Document + run identifiers and file info |
| Stage spans | `ingestion`, `parsing`, `cleaning`, `chunking`, `enrichment`, `vectorization` |
| LLM observations | Renamed to `Chunk Summary LLM`, `Document Summary LLM`, `Cleaning LLM`, etc. |
| Pixmap previews | Attached to the parsing span as media so you can preview page images directly in Langfuse[^1] |

[^1]: Langfuse automatically renders `data:<mime>;base64,<payload>` media per the [multi-modality documentation](https://langfuse.com/docs/observability/features/multi-modality).

## Navigating the UI

1. **Find a run**: Filter traces by the `session_id` (run UUID) or tags. Every stage + LLM call for that run will appear beneath a single trace.
2. **Inspect stages**: Open the span named after the pipeline stage to view structured metadata (chunk counts, cleaning report, enrichment summaries, etc.).
3. **Preview pixmaps**: Inside the parsing span, scroll to the `pixmap_previews` attachment list to view the actual images that were sent to the vision-enabled parser.
4. **Review LLM calls**: Child observations now use descriptive names (e.g., `Chunk Summary LLM`). Each observation captures:
   - model + usage
   - normalized prompt text (inputs had been missing before)
   - cleaned stage metadata (`pipeline_stage` attribute)
5. **Use sessions for diffing**: Because the session ID is the pipeline run ID, opening the “Sessions” tab in Langfuse shows every trace emitted while processing that document (LLM calls, embeddings, etc.) with consistent grouping.

## Tips

- **Filtering**: Save filters such as `tag:pipeline` + `metadata.filename:<doc>` to revisit the same artifact quickly.
- **Media privacy**: The multi-modal attachments reuse our existing storage paths; when you need to remove a run, delete the trace from Langfuse and remove the pixmaps from `artifacts/pixmaps/<doc_id>/`.
- **Stage correlation**: The `pipeline_stage` metadata makes it easy to chart latency per stage in the Langfuse Metrics tab without building a custom schema.
- **Replay**: Use the `input` column of a generation to replay the exact prompt in the Langfuse playground before editing prompts locally.

## Troubleshooting

| Symptom | Action |
| --- | --- |
| Trace shows multiple `document_pipeline` entries for the same run | Make sure the run ID passed to `PipelineRunner.run` is non-null so every span joins the same session. |
| Images don’t render in Langfuse | Verify the pixmap entry includes a `data:image/png;base64,...` URI. Regenerate the pixmaps if the file was deleted locally. |
| LLM observation still named `LlamaIndex_completion` | Update `PipelineLangfuseHandler` heuristics if you introduce a brand-new prompt; add a `PROMPT_LABELS` entry so the handler can rename it. |

For deeper architectural context see `docs/Pipeline_Data_Flow_and_Observability_Report.md`. For roadmap work items see `docs/Observability_Integration_TODO.md`.



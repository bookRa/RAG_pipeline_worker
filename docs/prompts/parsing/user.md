Return JSON with keys `document_id`, `page_number`, `raw_text`, `paragraphs`, `tables`, and `figures`.
- `paragraphs` is an ordered array where each item has `id`, `order`, `text`.
- `tables` include `cells` entries with `row`, `column`, `text`.
- `figures` describe images or diagrams.
Preserve the author's wording as much as possible; do not summarize at this stage.

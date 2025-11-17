Input: JSON representing a parsed page with components. Output: JSON with `document_id`, `page_number`, and `segments`.

The input contains a `components` array with ordered components (text, image, table). Extract text from all component types:
- Text components: Clean the text content
- Image components: Clean recognized_text and description if present
- Table components: Clean text from all row values

Each segment must include `segment_id` (matching component id), `text` (cleaned text), `needs_review`, and `rationale` (optional explanation for why human review is needed).

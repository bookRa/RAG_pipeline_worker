Return JSON with keys `document_id`, `page_number`, `raw_text`, `page_summary`, and `components`.

**Required Fields:**
- `document_id`: The document identifier
- `page_number`: The page number (1-indexed)
- `raw_text`: Full markdown representation of the page content (see system prompt for details)
- `page_summary`: A 2-3 sentence summary describing this page's role in the document and its key components
  - Explain what this page is about and its purpose
  - Mention key component types (e.g., "Contains a revision table and technical specifications")
  - Describe how this page fits into the overall document structure
- `components`: An ordered array of components reflecting the page layout from top to bottom, left to right

**Component Types:**

1. **Text Components** (`type: "text"`):
   - `id`: Unique identifier
   - `order`: Position in the components list (0-indexed, reflects visual order)
   - `text`: The text content
   - `text_type`: Optional type indicator ("paragraph", "heading", "caption", "label", etc.)
   - `bbox`: Optional bounding box coordinates
   
   Example:
   ```json
   {
     "type": "text",
     "id": "uuid",
     "order": 0,
     "text": "This is a paragraph of text.",
     "text_type": "paragraph"
   }
   ```

2. **Image Components** (`type: "image"`):
   - `id`: Unique identifier
   - `order`: Position in the components list
   - `description`: REQUIRED - Detailed VISUAL description of what is shown in the image
     - Describe what you see visually: shapes, colors, layout, objects, relationships
     - Do NOT copy text captions that appear near/below the image (those are separate text components)
     - Focus on describing the visual content of the image itself
   - `recognized_text`: Optional - Any text visible WITHIN the image itself (OCR results from text embedded in the image)
   - `bbox`: Optional bounding box coordinates
   
   Example:
   ```json
   {
     "type": "image",
     "id": "uuid",
     "order": 2,
     "description": "A diagram showing a three-tier architecture with three rectangular boxes arranged vertically, connected by downward-pointing arrows. The top box is labeled 'Web Server', middle box 'Application Server', and bottom box 'Database'. Each box has a light blue background.",
     "recognized_text": "Web Server\nApplication Server\nDatabase"
   }
   ```
   
   **IMPORTANT**: You must include EVERY image, diagram, figure, chart, graph, or visual element you see on the page. Do not skip any images.

3. **Table Components** (`type: "table"`):
   - `id`: Unique identifier
   - `order`: Position in the components list
   - `caption`: Optional table caption or title
   - `rows`: List of row dictionaries with flexible keys (handles merged cells, variable columns)
     - Each row is a dict with string keys and string values
     - Keys represent column names/identifiers
     - Values represent cell content
     - Different rows can have different keys (handles merged cells)
   - `table_summary`: REQUIRED - A 2-3 sentence summary of what the table shows
     - Describe the table's purpose and key information
     - Explain what data the table contains and what it represents
     - Example: "This table lists performance metrics for the system, showing response time, throughput, and error rate measurements with their units."
     - Always provide this summary even if the table is empty or simple
   - `bbox`: Optional bounding box coordinates
   
   Example:
   ```json
   {
     "type": "table",
     "id": "uuid",
     "order": 1,
     "caption": "Performance Metrics",
     "table_summary": "This table presents key performance metrics for the system, including response time (150ms), throughput (1000 req/s), and error rate (0.01%), with all measurements shown in their respective units.",
     "rows": [
       {"Metric": "Response Time", "Value": "150ms", "Unit": "milliseconds"},
       {"Metric": "Throughput", "Value": "1000", "Unit": "req/s"},
       {"Metric": "Error Rate", "Value": "0.01%", "Unit": "percentage"}
     ]
   }
   ```
   
   For merged cells, use the same key across multiple rows:
   ```json
   {
     "type": "table",
     "table_summary": "This table categorizes system components into Hardware (CPU and RAM) and Software (OS), showing their specifications.",
     "rows": [
       {"Category": "Hardware", "Item": "CPU", "Spec": "Intel i7"},
       {"Category": "Hardware", "Item": "RAM", "Spec": "16GB"},
       {"Category": "Software", "Item": "OS", "Spec": "Linux"}
     ]
   }
   ```

**Ordering Requirements:**
- Components MUST be ordered to reflect the visual layout of the page
- Process from top to bottom, left to right
- If an image appears before a paragraph, the image component should have a lower order number
- Maintain the reading flow of the document

**Thoroughness Requirements:**
- Extract EVERY visible text element as a text component
- Extract EVERY table as a table component
- Extract EVERY image, diagram, figure, chart as an image component
- Do not skip or omit any content
- If you see it on the page, it must be in the components list

Extract all content directly from the image. Do not use any pre-extracted text - read everything from the image itself.

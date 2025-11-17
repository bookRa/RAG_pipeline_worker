# Prompt Library

All LLM prompts are stored as markdown files under this directory, tracked in git alongside code. This enables version control, A/B testing, and easy rollback.

---

## Directory Structure

```
docs/prompts/
├── parsing/
│   ├── system.md               # LLM instructions for extracting components (with vision)
│   └── user.md                 # Output schema and examples
├── cleaning/
│   ├── system.md               # Text normalization rules and review criteria
│   └── user.md                 # Input format explanation
└── summarization/
    ├── system.md               # Generic summarization (legacy)
    ├── document_summary.md     # Document-level summary generation
    └── chunk_summary.md        # Chunk-level summary generation
```

---

## How Prompts Are Used in the Pipeline

### 1. Parsing Stage (LLM with Vision)

**Adapter**: `ImageAwareParsingAdapter` (`src/app/adapters/llama_index/parsing_adapter.py`)

**Inputs**:
- 300 DPI page image (PNG)
- Optional raw text from pdfplumber (for fallback)

**Prompts**:
- `parsing/system.md` - Instructions for identifying components (text, tables, images)
- `parsing/user.md` - JSON schema definition with examples

**Code Example**:

```python
# How prompts are loaded in the adapter
from src.app.prompts.loader import load_prompt

class ImageAwareParsingAdapter:
    def __init__(self, llm, vision_llm, prompt_settings):
        self._system_prompt = load_prompt("docs/prompts/parsing/system.md")
        self._user_prompt = load_prompt("docs/prompts/parsing/user.md")
    
    def parse_page(self, document_id, page_number, page_text, pixmap_path):
        # Build messages with image
        messages = [
            ChatMessage(role="system", content=self._system_prompt),
            ChatMessage(role="user", content=[
                ImageBlock(image=pixmap_path),
                TextBlock(text=self._user_prompt)
            ])
        ]
        
        # Use structured output for reliable JSON extraction
        structured_llm = self._vision_llm.as_structured_llm(ParsedPage)
        response = structured_llm.chat(messages)
        
        return response.raw  # Validated ParsedPage instance
```

**Output**: `ParsedPage` with components, table summaries, page summary

---

### 2. Cleaning Stage (LLM)

**Adapter**: `CleaningAdapter` (`src/app/adapters/llama_index/cleaning_adapter.py`)

**Inputs**:
- `ParsedPage` components from parsing stage
- Optional pixmap path (for vision-based cleaning)

**Prompts**:
- `cleaning/system.md` - Normalization rules, review criteria
- `cleaning/user.md` - How to interpret input format

**Code Example**:

```python
class CleaningAdapter:
    def __init__(self, llm, prompt_settings):
        self._system_prompt = load_prompt("docs/prompts/cleaning/system.md")
        self._user_prompt = load_prompt("docs/prompts/cleaning/user.md")
    
    def clean_page(self, parsed_page, pixmap_path=None):
        # Format components as prompt input
        input_text = self._format_components(parsed_page.components)
        
        # Use structured output
        structured_llm = self._llm.as_structured_llm(CleanedPage)
        prompt = f"{self._system_prompt}\n\n{self._user_prompt}\n\n{input_text}"
        response = structured_llm.complete(prompt)
        
        return response.raw  # Validated CleanedPage instance
```

**Output**: `CleanedPage` with cleaned text and flagged segments

---

### 3. Summarization Stage (LLM)

**Adapter**: `LlamaIndexSummaryAdapter` (`src/app/adapters/llama_index/summary_adapter.py`)

**Purpose**: Generate summaries at document and chunk levels with hierarchical context

**Prompts**:
- `summarization/document_summary.md` - Document-level summary generation (3-4 sentences)
- `summarization/chunk_summary.md` - Chunk-level summary generation (2 sentences)
- `summarization/system.md` - Generic summarization (legacy, for backwards compatibility)

---

#### Document Summary Generation

**Inputs**:
- Document filename and file type
- Total page count
- List of (page_number, page_summary) tuples

**Code Example**:

```python
class LlamaIndexSummaryAdapter:
    def __init__(self, llm, prompt_settings):
        self._document_summary_prompt = load_prompt("docs/prompts/summarization/document_summary.md")
    
    def summarize_document(self, filename, file_type, page_count, page_summaries):
        # Format page summaries for LLM
        formatted_summaries = "\n\n".join(
            f"**Page {page_num}**: {summary}" 
            for page_num, summary in page_summaries
        )
        
        user_content = f"""Document: {filename}
File Type: {file_type}
Total Pages: {page_count}

Page Summaries:
{formatted_summaries}
"""
        
        completion = self._llm.complete(f"{self._document_summary_prompt}\n\n{user_content}")
        return extract_response_text(completion).strip()
```

**Output**: 3-4 sentence summary capturing document type, main topics, key entities, and scope

---

#### Chunk Summary Generation

**Inputs**:
- Chunk text to summarize
- Hierarchical context (document title, document summary, page summary, component type)

**Code Example**:

```python
class LlamaIndexSummaryAdapter:
    def __init__(self, llm, prompt_settings):
        self._chunk_summary_prompt = load_prompt("docs/prompts/summarization/chunk_summary.md")
    
    def summarize_chunk(self, chunk_text, document_title, document_summary, 
                       page_summary, component_type):
        # Provide context to help LLM understand chunk's role
        user_content = f"""Context:
- Document title: {document_title}
- Document summary: {document_summary}
- Page summary: {page_summary or 'N/A'}
- Component type: {component_type or 'text'}

Chunk Text:
{chunk_text}
"""
        
        completion = self._llm.complete(f"{self._chunk_summary_prompt}\n\n{user_content}")
        return extract_response_text(completion).strip()
```

**Output**: 2-sentence summary (what the chunk contains + how it relates to the document)

---

## Prompt Tuning Guide

### Quick Workflow

1. **Edit prompt file**: Modify `docs/prompts/{stage}/system.md`
2. **Restart server**: Prompts are loaded at startup
3. **Test via dashboard**: Upload document at `http://localhost:8000/dashboard`
4. **Inspect output**: Check `artifacts/documents/{doc_id}.json`
5. **Iterate**: Repeat until quality improves

### Testing Prompt Changes

**Before/After Comparison**:

```bash
# 1. Process document with current prompts
curl -X POST http://localhost:8000/upload -F "file=@test.pdf"
# Save output: artifacts/documents/{doc_id}.json

# 2. Edit prompt
vim docs/prompts/parsing/system.md

# 3. Restart server
pkill -f uvicorn && uvicorn src.app.main:app --reload &

# 4. Reprocess same document
curl -X POST http://localhost:8000/upload -F "file=@test.pdf"
# Compare new output to saved version
```

---

## Common Tuning Scenarios

### Improving Table Extraction

**Problem**: Tables missing rows or columns

**Solution**: Update `parsing/system.md`:

```markdown
# Before
Extract any tables you find in the document.

# After
Extract ALL tables with these requirements:
- Capture EVERY row and column
- Include table captions/titles
- Generate a 2-sentence summary describing the table's purpose
- Preserve numerical data exactly as shown
```

**Test**: Upload document with complex tables, verify all rows/columns present

---

### Reducing False Positive Review Flags

**Problem**: Too many segments flagged for review unnecessarily

**Solution**: Update `cleaning/system.md`:

```markdown
# Before
Flag any segment that might need human review.

# After
Flag segments for review ONLY if they contain:
1. Contact information (email, phone, address)
2. Version numbers or dates that may be outdated
3. Technical specifications with measurements
4. Legal disclaimers or safety warnings

DO NOT flag:
- General descriptive text
- Common terminology
- Well-formatted paragraphs
```

**Test**: Compare `needs_review` counts before/after change

---

### Improving Summary Quality

**Problem**: Summaries too generic or verbose

**Solution**: Update `summarization/system.md`:

```markdown
# Before
Summarize the following text.

# After
Generate a 2-sentence summary that:
- Captures the MAIN point or purpose
- Includes key specific details (numbers, names, dates)
- Uses active voice
- Avoids generic phrases like "this section discusses"

Example:
Input: "The propeller has a diameter of 72 inches and operates at 2400 RPM..."
Output: "The propeller measures 72 inches in diameter and operates at 2400 RPM. Maximum thrust is 850 pounds at sea level."
```

**Test**: Read 10 random chunk summaries, verify they're specific and concise

---

## Prompt Version Management

### Git-Based Versioning

Prompts are tracked in git, so every change creates a commit:

```bash
# Make prompt changes
vim docs/prompts/parsing/system.md

# Commit with descriptive message
git add docs/prompts/parsing/system.md
git commit -m "Improve table extraction: require captions and summaries"

# Test quality
# ... upload test documents ...

# Rollback if needed
git revert HEAD
```

### A/B Testing

Compare prompt versions on the same documents:

```bash
# Branch A: current prompts
git checkout main
./test_documents.sh > results_main.json

# Branch B: experimental prompts
git checkout feature/improved-parsing
./test_documents.sh > results_experimental.json

# Compare outputs
diff results_main.json results_experimental.json
```

---

## Troubleshooting

### Prompt Not Taking Effect

**Symptoms**: Changes to prompt file don't affect output

**Solutions**:
1. Restart server (prompts loaded at startup)
2. Check file path is correct (`docs/prompts/...`, not `src/app/prompts/...`)
3. Verify no syntax errors in markdown

### Inconsistent Results

**Symptoms**: Same prompt produces different outputs

**Solutions**:
1. Check LLM temperature setting (lower = more consistent)
2. Add explicit examples in prompt
3. Use structured outputs (`as_structured_llm()`) for JSON

### LLM Not Following Instructions

**Symptoms**: Output doesn't match prompt instructions

**Solutions**:
1. Make instructions more explicit and specific
2. Add examples of correct output
3. Use negative examples ("DO NOT...")
4. Simplify prompt (shorter often = better)

---

## Best Practices

### 1. Be Specific

**Bad**: "Extract tables from the document"  
**Good**: "Extract ALL tables. For each table, capture every row and column exactly as shown, include the caption/title, and generate a 2-sentence summary describing what data the table contains."

### 2. Provide Examples

```markdown
Generate summaries following this format:

Example Input:
"The aircraft has a wingspan of 35 feet and weighs 2,400 pounds..."

Example Output:
"The aircraft features a 35-foot wingspan and weighs 2,400 pounds empty. Maximum takeoff weight is 3,200 pounds with full fuel."
```

### 3. Use Structured Outputs

For JSON output, use LlamaIndex's `as_structured_llm()` with Pydantic models instead of describing JSON structure in prompts.

### 4. Test on Edge Cases

Don't just test on perfect documents. Test on:
- Scanned documents (OCR artifacts)
- Complex tables (merged cells, nested headers)
- Mixed content (diagrams + tables + text)
- Multi-column layouts

### 5. Version Your Changes

Every prompt change should be a git commit with a clear message explaining why the change was made and what it aims to improve.

---

## Future: Langfuse Integration

**Coming soon**: Migrate prompts to Langfuse for:
- UI-based prompt editing
- Automatic version tracking
- A/B testing built-in
- Quality metrics per prompt version

See [`Observability_Integration_TODO.md`](../Observability_Integration_TODO.md) for timeline.

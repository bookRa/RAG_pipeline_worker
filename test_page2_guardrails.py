#!/usr/bin/env python3
"""Test guardrails specifically on page 2 of doc_short_noisy.pdf."""
import logging
import sys
from pathlib import Path

# Enable DEBUG logging
logging.basicConfig(level=logging.INFO)
logging.getLogger('rag_pipeline.llm').setLevel(logging.DEBUG)

from src.app.adapters.llama_index.factory import get_llama_llm
from src.app.adapters.llama_index.parsing_adapter import ImageAwareParsingAdapter
from src.app.config import settings

def main():
    """Test parsing page 2 with guardrails."""
    # Setup
    llm = get_llama_llm()
    adapter = ImageAwareParsingAdapter(
        llm=llm,
        prompt_settings=settings.prompts,
        use_structured_outputs=True,
        use_streaming=True,
        streaming_max_chars=50000,
        streaming_repetition_window=200,
        streaming_repetition_threshold=0.8,
        streaming_max_consecutive_newlines=100,
    )
    
    # Page 2 pixmap from doc_short_noisy.pdf
    pixmap_path = "artifacts/pixmaps/test_guardrails_v2/page_0002.png"
    if not Path(pixmap_path).exists():
        print(f"ERROR: {pixmap_path} not found")
        print("Run the full parsing first to generate pixmaps")
        return 1
    
    print("=" * 80)
    print("🧪 Testing Page 2 with Enhanced Guardrails")
    print("=" * 80)
    print("Watch for:")
    print("  🛡️  = Guardrail configuration")
    print("  🔍  = Guardrail checks (every 50 chunks)")
    print("  ⚠️   = Guardrail triggered!")
    print("=" * 80)
    
    try:
        result = adapter.parse_page(
            document_id="test_page2",
            page_number=2,
            pixmap_path=pixmap_path,
        )
        
        print("=" * 80)
        if result:
            print(f"✅ SUCCESS: Parsed {len(result.components)} components")
            print(f"   Raw text length: {len(result.raw_text)} chars")
        else:
            print("⚠️  WARNING: Returned None (possibly empty page)")
            
        return 0
        
    except KeyboardInterrupt:
        print("\n⏹️  Interrupted by user")
        return 130
    except Exception as e:
        print("=" * 80)
        print(f"❌ ERROR: {e}")
        import traceback
        traceback.print_exc()
        return 1

if __name__ == '__main__':
    sys.exit(main())



#!/usr/bin/env python3
"""Proof of concept: Test if as_structured_llm() works with vision.

This script tests whether LlamaIndex's structured output API (as_structured_llm())
is compatible with vision-enabled models that accept ImageBlock content.

Usage:
    # Set your OpenAI API key
    export OPENAI_API_KEY=sk-...
    
    # Run the test
    python tests/poc_structured_vision.py
    
Expected outcome:
    ✅ SUCCESS: Structured LLM works with vision!
    OR
    ❌ FAILURE: Structured LLM doesn't support vision

If this test passes, we can proceed with implementing structured outputs for parsing.
If it fails, we'll need to keep manual schema injection for vision-based parsing.
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

# Add parent directory to path so we can import from src
sys.path.insert(0, str(Path(__file__).parent.parent))

from pydantic import BaseModel, Field


class SimplePageStructure(BaseModel):
    """Simple test schema for POC."""
    description: str = Field(description="Describe what you see in the image")
    has_text: bool = Field(description="Does the image contain text?")
    has_table: bool = Field(description="Does the image contain a table?")
    has_image: bool = Field(description="Does the image contain figures/diagrams?")
    element_count: int = Field(description="Approximate number of distinct elements")
    confidence: float = Field(ge=0.0, le=1.0, description="Confidence in analysis")


def create_test_image(path: Path) -> None:
    """Create a simple test image with text and shapes."""
    try:
        from PIL import Image, ImageDraw, ImageFont
    except ImportError:
        print("❌ ERROR: Pillow is required. Install with: pip install Pillow")
        sys.exit(1)
    
    # Create a simple test image with text and shapes
    img = Image.new("RGB", (400, 300), color="white")
    draw = ImageDraw.Draw(img)
    
    # Try to use a nice font, fall back to default
    try:
        font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 24)
        small_font = ImageFont.truetype("/System/Library/Fonts/Helvetica.ttc", 16)
    except Exception:
        font = ImageFont.load_default()
        small_font = ImageFont.load_default()
    
    # Add a title
    draw.text((20, 20), "Test Document", fill="black", font=font)
    
    # Add some body text
    draw.text((20, 60), "This is a test page for structured", fill="black", font=small_font)
    draw.text((20, 85), "output proof-of-concept testing.", fill="black", font=small_font)
    
    # Draw a simple table
    table_x = 20
    table_y = 130
    cell_width = 120
    cell_height = 30
    
    # Table header
    draw.rectangle([table_x, table_y, table_x + cell_width * 2, table_y + cell_height], outline="black")
    draw.text((table_x + 5, table_y + 5), "Column A", fill="black", font=small_font)
    draw.text((table_x + cell_width + 5, table_y + 5), "Column B", fill="black", font=small_font)
    
    # Table row
    draw.rectangle([table_x, table_y + cell_height, table_x + cell_width * 2, table_y + cell_height * 2], outline="black")
    draw.text((table_x + 5, table_y + cell_height + 5), "Value 1", fill="black", font=small_font)
    draw.text((table_x + cell_width + 5, table_y + cell_height + 5), "Value 2", fill="black", font=small_font)
    
    # Draw a simple diagram (circle)
    draw.ellipse([300, 130, 370, 200], outline="blue", width=2)
    draw.text((315, 160), "Diagram", fill="blue", font=small_font)
    
    img.save(path)
    print(f"✓ Created test image: {path}")


def test_structured_llm_with_vision() -> bool:
    """Test if structured LLM works with vision input.
    
    Returns:
        True if test passes, False if it fails
    """
    # Check for API key
    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        print("❌ ERROR: OPENAI_API_KEY environment variable not set")
        print("   Set it with: export OPENAI_API_KEY=sk-...")
        return False
    
    print(f"✓ Found OPENAI_API_KEY (length: {len(api_key)})")
    
    # Import LlamaIndex components
    try:
        from llama_index.llms.openai import OpenAI
        from llama_index.core.llms import ChatMessage
        from llama_index.core.base.llms.types import ImageBlock
        from llama_index.core.multi_modal_llms.generic_utils import encode_image
    except ImportError as exc:
        print(f"❌ ERROR: Failed to import LlamaIndex: {exc}")
        print("   Install with: pip install llama-index llama-index-llms-openai")
        return False
    
    print("✓ LlamaIndex imports successful")
    
    # Create test image
    test_img_path = Path("/tmp/test_vision_structured_output.png")
    create_test_image(test_img_path)
    
    # Create LLM
    print("\n" + "="*60)
    print("Testing: OpenAI GPT-4o-mini with structured outputs + vision")
    print("="*60 + "\n")
    
    try:
        llm = OpenAI(model="gpt-4o-mini", temperature=0.0)
        print("✓ Created OpenAI LLM instance")
    except Exception as exc:
        print(f"❌ ERROR: Failed to create LLM: {exc}")
        return False
    
    # Create structured wrapper
    try:
        structured_llm = llm.as_structured_llm(SimplePageStructure)
        print("✓ Created structured LLM wrapper with as_structured_llm()")
    except Exception as exc:
        print(f"❌ ERROR: Failed to create structured LLM wrapper: {exc}")
        return False
    
    # Encode image
    try:
        image_data = encode_image(str(test_img_path))
        print("✓ Encoded test image as base64")
    except Exception as exc:
        print(f"❌ ERROR: Failed to encode image: {exc}")
        return False
    
    # Create messages with image
    try:
        messages = [
            ChatMessage(
                role="system",
                content="Analyze the image and respond with structured data about what you see."
            ),
            ChatMessage(
                role="user",
                content=[
                    ImageBlock(image=image_data, image_mimetype="image/png"),
                ],
            ),
        ]
        print("✓ Created chat messages with ImageBlock")
    except Exception as exc:
        print(f"❌ ERROR: Failed to create messages: {exc}")
        return False
    
    # Try to call chat() on structured LLM
    print("\n🔄 Calling structured_llm.chat() with vision input...")
    try:
        response = structured_llm.chat(messages)
        print("✓ Chat call succeeded!")
    except Exception as exc:
        print(f"❌ ERROR: Chat call failed: {type(exc).__name__}: {exc}")
        print("\n📝 Diagnosis:")
        print("   The structured LLM wrapper doesn't support vision (ImageBlock) input.")
        print("   This means we need to keep manual schema injection for parsing.")
        return False
    
    # Check if response has .raw attribute with Pydantic model
    print("\n🔍 Checking response format...")
    
    if hasattr(response, "raw"):
        print("✓ Response has .raw attribute")
        
        if isinstance(response.raw, SimplePageStructure):
            print("✓ response.raw is a SimplePageStructure instance")
            print("\n" + "="*60)
            print("✅ SUCCESS: Structured LLM works with vision!")
            print("="*60)
            print("\n📊 Structured Output:")
            print(f"   Description: {response.raw.description}")
            print(f"   Has Text: {response.raw.has_text}")
            print(f"   Has Table: {response.raw.has_table}")
            print(f"   Has Image: {response.raw.has_image}")
            print(f"   Element Count: {response.raw.element_count}")
            print(f"   Confidence: {response.raw.confidence}")
            print("\n✅ We can proceed with implementing structured outputs for parsing!")
            return True
        else:
            print(f"❌ response.raw is wrong type: {type(response.raw)}")
            print(f"   Expected: SimplePageStructure")
            print(f"   Got: {type(response.raw).__name__}")
    else:
        print("❌ Response doesn't have .raw attribute")
        print(f"   Response type: {type(response)}")
        print(f"   Response attributes: {dir(response)}")
    
    # Try alternative extraction methods
    print("\n🔍 Trying alternative extraction methods...")
    
    if hasattr(response, "text"):
        print(f"✓ Response has .text attribute: {response.text[:100]}...")
        try:
            parsed = SimplePageStructure.model_validate_json(response.text)
            print("✓ Manually parsed text as JSON")
            print("\n⚠️  PARTIAL SUCCESS: Structured output works, but requires manual parsing")
            print("   (response.raw not available, need to parse response.text)")
            return True
        except Exception as exc:
            print(f"❌ Failed to parse text as JSON: {exc}")
    
    if hasattr(response, "message"):
        print(f"✓ Response has .message attribute")
        if hasattr(response.message, "content"):
            content = response.message.content
            print(f"   Message content type: {type(content)}")
            if isinstance(content, str):
                print(f"   Content (first 100 chars): {content[:100]}...")
    
    print("\n" + "="*60)
    print("❌ FAILURE: Structured LLM doesn't properly support vision")
    print("="*60)
    print("\n📝 Recommendation:")
    print("   Keep manual schema injection for vision-based parsing.")
    print("   Consider using structured outputs for non-vision text parsing only.")
    
    return False


def main():
    """Run the proof-of-concept test."""
    print("\n" + "="*60)
    print("Proof of Concept: Structured Outputs + Vision")
    print("="*60 + "\n")
    
    success = test_structured_llm_with_vision()
    
    print("\n" + "="*60)
    if success:
        print("RESULT: ✅ TEST PASSED")
        print("\nNext steps:")
        print("1. Proceed with Phase 1 of implementation plan")
        print("2. Add _parse_with_structured_api() method to parsing adapter")
        print("3. Update tests to verify structured output usage")
    else:
        print("RESULT: ❌ TEST FAILED")
        print("\nNext steps:")
        print("1. Document this limitation in the codebase")
        print("2. Keep manual schema injection for vision-based parsing")
        print("3. Consider using structured outputs for non-vision stages only")
        print("4. File issue with LlamaIndex project about vision support")
    print("="*60 + "\n")
    
    return 0 if success else 1


if __name__ == "__main__":
    sys.exit(main())


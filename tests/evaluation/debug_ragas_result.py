"""Debug script to inspect Ragas EvaluationResult structure.

Run this with: RUN_RAG_TESTS=1 python tests/evaluation/debug_ragas_result.py
"""

import os
import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

try:
    from ragas import evaluate
    from ragas.metrics import faithfulness, answer_relevancy, context_precision, context_recall
    from tests.evaluation.rag_eval_dataset import load_eval_dataset
except ImportError as e:
    print(f"❌ Import error: {e}")
    print("Make sure Ragas and datasets are installed:")
    print("  pip install ragas datasets")
    sys.exit(1)

def inspect_result(result):
    """Inspect the structure of a Ragas EvaluationResult."""
    print("\n" + "=" * 80)
    print("RAGAS RESULT INSPECTION")
    print("=" * 80)
    
    print(f"\n1. Result type: {type(result)}")
    print(f"   Module: {type(result).__module__}")
    print(f"   Class name: {type(result).__name__}")
    
    print(f"\n2. Result attributes (non-private):")
    attrs = [attr for attr in dir(result) if not attr.startswith('_')]
    for attr in attrs[:20]:  # Show first 20
        try:
            value = getattr(result, attr)
            value_type = type(value).__name__
            if not callable(value):
                print(f"   - {attr}: {value_type} = {value}")
            else:
                print(f"   - {attr}: {value_type}()")
        except Exception as e:
            print(f"   - {attr}: ERROR - {e}")
    
    print(f"\n3. Direct metric access attempts:")
    for metric in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        if hasattr(result, metric):
            value = getattr(result, metric)
            print(f"   - {metric}: {type(value).__name__} = {value}")
    
    print(f"\n4. to_pandas() method:")
    if hasattr(result, "to_pandas"):
        try:
            df = result.to_pandas()
            print(f"   ✅ Success!")
            print(f"   Shape: {df.shape}")
            print(f"   Columns: {list(df.columns)}")
            print(f"\n   DataFrame head:")
            print(df.head().to_string())
            print(f"\n   DataFrame dtypes:")
            print(df.dtypes)
            
            # Try to extract metrics
            print(f"\n   Metric extraction attempts:")
            for col in df.columns:
                if col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                    try:
                        mean_val = df[col].mean()
                        print(f"   - {col}: mean = {mean_val}")
                    except Exception as e:
                        print(f"   - {col}: ERROR - {e}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    else:
        print("   ❌ Method not available")
    
    print(f"\n5. to_dict() method:")
    if hasattr(result, "to_dict"):
        try:
            data = result.to_dict()
            print(f"   ✅ Success!")
            print(f"   Type: {type(data)}")
            if isinstance(data, dict):
                print(f"   Keys: {list(data.keys())[:10]}")
                for key in list(data.keys())[:5]:
                    print(f"   - {key}: {type(data[key]).__name__} = {data[key]}")
        except Exception as e:
            print(f"   ❌ Failed: {e}")
    else:
        print("   ❌ Method not available")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    if os.getenv("RUN_RAG_TESTS") != "1":
        print("⚠️  Set RUN_RAG_TESTS=1 to run this script")
        sys.exit(0)
    
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM__API_KEY")
    if not api_key:
        print("⚠️  OPENAI_API_KEY or LLM__API_KEY must be set")
        sys.exit(0)
    
    print("Loading evaluation dataset...")
    dataset = load_eval_dataset()
    
    if isinstance(dataset, dict):
        print("❌ Dataset is a dict, not a Dataset object. Install 'datasets' package.")
        sys.exit(1)
    
    print("Running Ragas evaluation...")
    print("(This may take a minute...)")
    
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )
    
    inspect_result(result)


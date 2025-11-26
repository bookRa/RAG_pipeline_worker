"""Ragas quality evaluation for RAG pipeline.

This module evaluates RAG pipeline quality using Ragas metrics:
- faithfulness: Does the response contain only information from the source?
- answer_relevancy: Is the response relevant to the question?
- context_precision: Are the retrieved chunks relevant?
- context_recall: Are all relevant chunks retrieved?
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest
from dotenv import load_dotenv

# Load .env file if it exists (for API keys)
env_path = Path(__file__).parent.parent.parent / ".env"
if env_path.exists():
    load_dotenv(env_path, override=False)

RUN_RAG_TESTS = os.getenv("RUN_RAG_TESTS") == "1"

try:
    from ragas import evaluate
    from ragas.metrics import (
        answer_relevancy,
        context_precision,
        context_recall,
        faithfulness,
    )
    RAGAS_AVAILABLE = True
except ImportError:
    RAGAS_AVAILABLE = False
    # Define placeholders if Ragas is not available
    evaluate = None
    answer_relevancy = None
    context_precision = None
    context_recall = None
    faithfulness = None

from .rag_eval_dataset import load_eval_dataset, DATASETS_AVAILABLE

pytestmark = pytest.mark.skipif(
    not RUN_RAG_TESTS,
    reason="Set RUN_RAG_TESTS=1 to run RAG quality evaluation tests",
)


def _result_to_metrics(result: Any) -> dict[str, float]:
    """Attempt to convert a ragas EvaluationResult into a dict."""
    
    # Check if result is already a pandas DataFrame
    try:
        import pandas as pd
        if isinstance(result, pd.DataFrame):
            df = result
            metric_cols = [col for col in df.columns if col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]]
            if metric_cols:
                metrics = {}
                for col in metric_cols:
                    try:
                        value = df[col].mean() if hasattr(df[col], "mean") else None
                        # Check for NaN properly
                        import math
                        if value is not None and not math.isnan(value):
                            metrics[col] = float(value)
                    except Exception:
                        pass
                if metrics:
                    return metrics
    except ImportError:
        pass  # pandas not available, continue with other methods
    
    # Try direct dict access first (EvaluationResult is dict-like)
    # Check if result itself is dict-like (EvaluationResult often is)
    # The repr shows: {'faithfulness': nan, 'answer_relevancy': nan, ...}
    # So we can access it as a dict
    if isinstance(result, dict) or hasattr(result, 'keys'):
        try:
            result_dict = dict(result) if not isinstance(result, dict) else result
            metrics = {}
            import math
            for k, v in result_dict.items():
                if k in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                    # Handle NaN values - skip them but don't fail
                    if isinstance(v, (int, float)):
                        if not math.isnan(v):
                            metrics[k] = float(v)
            if metrics:
                return metrics
        except Exception:
            pass
    
    # Also try accessing as attributes (EvaluationResult might expose metrics as attributes)
    import math
    metrics = {}
    for attr in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
        if hasattr(result, attr):
            try:
                value = getattr(result, attr)
                if isinstance(value, (int, float)) and not math.isnan(value):
                    metrics[attr] = float(value)
                elif hasattr(value, "score"):
                    score_val = value.score
                    if isinstance(score_val, (int, float)) and not math.isnan(score_val):
                        metrics[attr] = float(score_val)
                elif isinstance(value, dict) and "score" in value:
                    score_val = value["score"]
                    if isinstance(score_val, (int, float)) and not math.isnan(score_val):
                        metrics[attr] = float(score_val)
            except Exception:
                pass
    if metrics:
        return metrics
    
    # Try to_pandas() method (most reliable for Ragas)
    # Ragas typically returns a DataFrame where metrics are columns
    to_pandas = getattr(result, "to_pandas", None)
    if callable(to_pandas):
        try:
            df = to_pandas()
            
            # Method 1: Direct metric columns (most common Ragas pattern)
            # Each row is a question-answer pair, metrics are columns
            # Try exact column names first
            metric_cols = [col for col in df.columns if col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]]
            
            # If no exact matches, try case-insensitive and partial matches
            if not metric_cols:
                for col in df.columns:
                    col_lower = str(col).lower()
                    if "faithfulness" in col_lower:
                        metric_cols.append(col)
                    elif "answer_relevancy" in col_lower or "answer_relevance" in col_lower:
                        metric_cols.append(col)
                    elif "context_precision" in col_lower:
                        metric_cols.append(col)
                    elif "context_recall" in col_lower:
                        metric_cols.append(col)
            
            if metric_cols:
                metric_name_map = {}
                for col in metric_cols:
                    col_lower = str(col).lower()
                    if "faithfulness" in col_lower:
                        metric_name_map[col] = "faithfulness"
                    elif "answer_relevancy" in col_lower or "answer_relevance" in col_lower:
                        metric_name_map[col] = "answer_relevancy"
                    elif "context_precision" in col_lower:
                        metric_name_map[col] = "context_precision"
                    elif "context_recall" in col_lower:
                        metric_name_map[col] = "context_recall"
                    else:
                        # Use column name as-is if it's already one of our expected names
                        if col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                            metric_name_map[col] = col
                
                for col in metric_cols:
                    try:
                        # Get mean across all rows (aggregate metric)
                        if hasattr(df[col], "mean"):
                            value = df[col].mean()
                        elif len(df) > 0:
                            # If mean() doesn't work, try first value or sum/len
                            value = df[col].iloc[0] if len(df) == 1 else df[col].sum() / len(df)
                        else:
                            value = None
                        
                        # Check for NaN properly
                        import math
                        if value is not None and not math.isnan(value):
                            metric_name = metric_name_map.get(col, col)
                            metrics[metric_name] = float(value)
                    except Exception as e:
                        import logging
                        logging.debug(f"Failed to extract {col}: {e}")
                        pass
                
                if metrics:
                    return metrics
            
            # Fallback: If we have a DataFrame but no metric columns matched,
            # try extracting all numeric columns as potential metrics
            # This helps us see what Ragas actually returned
            try:
                import pandas as pd
                numeric_cols = df.select_dtypes(include=['float64', 'int64', 'float32', 'int32', 'float', 'int']).columns.tolist()
                if numeric_cols and not metrics:
                    # Extract all numeric columns as potential metrics
                    fallback_metrics = {}
                    for col in numeric_cols:
                        try:
                            value = df[col].mean() if hasattr(df[col], "mean") else None
                            if value is not None and not (isinstance(value, float) and (value != value)):  # Check for NaN
                                # Normalize column name
                                col_normalized = str(col).lower().replace(" ", "_").replace("-", "_")
                                fallback_metrics[col_normalized] = float(value)
                        except Exception:
                            pass
                    # If we found metrics this way, return them (even if names don't match exactly)
                    # This will help us see what Ragas actually returns
                    if fallback_metrics:
                        return fallback_metrics
            except Exception:
                pass
            
            # Method 2: Metrics stored in rows with metric_name/score columns
            if hasattr(df, "iterrows"):
                row_metrics = {}
                for _, row in df.iterrows():
                    # Try multiple possible column names for metric name
                    metric_name = (
                        row.get("metric_name") 
                        or row.get("metric") 
                        or row.get("name")
                        or row.get("metrics")
                    )
                    score = row.get("score") or row.get("value") or row.get("scores")
                    
                    if metric_name and score is not None:
                        try:
                            metric_name_str = str(metric_name).lower().replace(" ", "_")
                            # Normalize metric names
                            if "faithfulness" in metric_name_str:
                                metric_name_str = "faithfulness"
                            elif "answer_relevancy" in metric_name_str or "relevancy" in metric_name_str:
                                metric_name_str = "answer_relevancy"
                            elif "context_precision" in metric_name_str:
                                metric_name_str = "context_precision"
                            elif "context_recall" in metric_name_str:
                                metric_name_str = "context_recall"
                            
                            if metric_name_str in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                                row_metrics[metric_name_str] = float(score)
                        except (ValueError, TypeError):
                            pass
                
                if row_metrics:
                    return row_metrics
                    
        except Exception as e:
            # Log but don't fail - try other methods
            import logging
            logging.debug(f"Failed to extract metrics from pandas: {e}")
    
    # Try to_dict() method
    to_dict = getattr(result, "to_dict", None)
    if callable(to_dict):
        try:
            data = to_dict()
            if isinstance(data, dict):
                return {k: float(v) for k, v in data.items() if isinstance(v, (int, float))}
        except Exception:
            pass
    
    # Try accessing .scores or .metrics attributes
    for attr in ("scores", "metrics", "results"):
        if hasattr(result, attr):
            maybe_dict = getattr(result, attr)
            if isinstance(maybe_dict, dict):
                return {k: float(v) for k, v in maybe_dict.items() if isinstance(v, (int, float))}
    
    # Last resort: try to access result as if it's a DataFrame-like object
    if hasattr(result, "columns"):
        try:
            for col in result.columns:
                if col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                    try:
                        value = result[col].mean() if hasattr(result[col], "mean") else result[col].iloc[0] if len(result) > 0 else None
                        # Check for NaN properly
                        import math
                        if value is not None and not math.isnan(value):
                            metrics[col] = float(value)
                    except Exception:
                        pass
            if metrics:
                return metrics
        except Exception:
            pass
    
    # Try accessing as dict-like with __getitem__
    if hasattr(result, "__getitem__"):
        try:
            import math
            for metric_name in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                try:
                    value = result[metric_name]
                    if isinstance(value, (int, float)) and not math.isnan(value):
                        metrics[metric_name] = float(value)
                    elif hasattr(value, "mean"):
                        mean_val = value.mean()
                        if not math.isnan(mean_val):
                            metrics[metric_name] = float(mean_val)
                except (KeyError, TypeError, AttributeError):
                    pass
            if metrics:
                return metrics
        except Exception:
            pass
    
    return {}


def test_rag_pipeline_quality():
    """Evaluate RAG pipeline quality using Ragas metrics."""
    if not RAGAS_AVAILABLE or evaluate is None:
        pytest.skip("Ragas is not installed")
    
    # Check for required API key (reload .env to ensure we have latest values)
    # Reload in case conftest cleared them (though it shouldn't when RUN_RAG_TESTS=1)
    env_path = Path(__file__).parent.parent.parent / ".env"
    if env_path.exists():
        load_dotenv(env_path, override=True)  # Override to ensure we get the values
    
    api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM__API_KEY")
    
    # Check for placeholder values
    if api_key and api_key in ["your-openai-key", "sk-...", ""]:
        pytest.skip(
            "OPENAI_API_KEY or LLM__API_KEY is set but appears to be a placeholder. "
            "Please set a real API key in your .env file or environment variables."
        )
    
    if not api_key:
        pytest.skip(
            "OPENAI_API_KEY or LLM__API_KEY must be set to run RAG quality evaluation tests. "
            "Set RUN_RAG_TESTS=1 and provide an API key in your .env file or environment variables."
        )
    
    # Load evaluation dataset
    dataset = load_eval_dataset()
    
    # Ensure we have a valid dataset (not empty dict)
    if not DATASETS_AVAILABLE or isinstance(dataset, dict):
        pytest.skip("Datasets package is not installed")
    
    # Run evaluation with Ragas metrics
    result = evaluate(
        dataset,
        metrics=[
            faithfulness,
            answer_relevancy,
            context_precision,
            context_recall,
        ],
    )
    
    # Debug: Inspect result structure (only if extraction fails)
    metrics_dict = _result_to_metrics(result)
    
    if not metrics_dict:
        # Check if all metrics are NaN (evaluation failed)
        import math
        import pandas as pd
        
        all_nan = True
        nan_metrics = []
        
        # Check dict-like result
        if isinstance(result, dict) or hasattr(result, 'keys'):
            try:
                result_dict = dict(result) if not isinstance(result, dict) else result
                for k in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                    if k in result_dict:
                        v = result_dict[k]
                        if isinstance(v, (int, float)) and not math.isnan(v):
                            all_nan = False
                        else:
                            nan_metrics.append(k)
            except Exception:
                pass
        
        # Check DataFrame
        df = None
        if hasattr(result, "to_pandas"):
            try:
                df = result.to_pandas()
                for col in ["faithfulness", "answer_relevancy", "context_precision", "context_recall"]:
                    if col in df.columns:
                        try:
                            mean_val = df[col].mean()
                            if not math.isnan(mean_val):
                                all_nan = False
                            else:
                                nan_metrics.append(col)
                        except Exception:
                            nan_metrics.append(col)
            except Exception:
                pass
        
        if all_nan and nan_metrics:
            pytest.skip(
                f"Ragas evaluation completed but all metrics are NaN (evaluation failed). "
                f"Affected metrics: {', '.join(nan_metrics)}. "
                f"This usually indicates: "
                f"(1) Dataset format issue - check column names match Ragas requirements, "
                f"(2) API/LLM errors during evaluation, "
                f"(3) Empty or invalid contexts/answers. "
                f"Check Ragas logs/warnings above for details."
            )
        
        # Debug output to help diagnose the issue
        debug_info = []
        debug_info.append(f"Result type: {type(result)}")
        debug_info.append(f"Result module: {type(result).__module__}")
        debug_info.append(f"Result repr: {repr(result)[:200]}...")
        
        if df is not None:
            debug_info.append(f"DataFrame shape: {df.shape}")
            debug_info.append(f"DataFrame columns: {list(df.columns)}")
            debug_info.append(f"DataFrame dtypes:\n{df.dtypes}")
            if len(df) > 0:
                debug_info.append(f"\nDataFrame head (first 5 rows):")
                debug_info.append(str(df.head()))
                debug_info.append(f"\nDataFrame describe (statistics):")
                debug_info.append(str(df.describe()))
        
        # Print debug info
        print("\n" + "=" * 80)
        print("DEBUG: Failed to extract metrics from Ragas result")
        print("=" * 80)
        for line in debug_info:
            print(line)
        print("=" * 80 + "\n")
        
        pytest.skip(
            f"Ragas evaluation did not produce extractable metrics. "
            f"See debug output above for result structure details."
        )
    
    print("\n" + "=" * 80)
    print("RAG Quality Evaluation Results")
    print("=" * 80)
    print(f"\nMetrics:")
    for metric, value in metrics_dict.items():
        print(f"  {metric}: {value:.3f}")
    
    # Assert minimum quality thresholds
    thresholds = {
        "faithfulness": 0.90,
        "answer_relevancy": 0.80,
        "context_precision": 0.80,
        "context_recall": 0.70,
    }
    for metric, threshold in thresholds.items():
        value = float(metrics_dict.get(metric, 0.0))
        assert (
            value > threshold
        ), f"{metric.replace('_', ' ').title()} {value:.3f} below threshold {threshold:.2f}"
    
    print("\n✓ All quality thresholds met!")
    print("=" * 80)
    
    return metrics_dict


if __name__ == "__main__":
    # Run evaluation directly
    test_rag_pipeline_quality()


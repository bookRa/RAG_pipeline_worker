# RAG Quality Evaluation Test - Troubleshooting Guide

## Current Status

The RAG quality evaluation test (`tests/evaluation/test_rag_quality.py`) is currently skipping because **all metrics are returning NaN (Not a Number)**, which indicates the Ragas evaluation completed but failed to compute metrics.

## What's Happening

When you run `RUN_RAG_TESTS=1 pytest tests/evaluation/test_rag_quality.py -v -s`, you'll see:

1. ✅ **Evaluation runs**: Ragas processes the dataset (progress bar shows 100%)
2. ✅ **Dataset format is correct**: Ragas accepts and converts the dataset properly
3. ❌ **Metrics are NaN**: All metric columns (`faithfulness`, `answer_relevancy`, `context_precision`, `context_recall`) contain NaN values

## Why Metrics Are NaN

When Ragas metrics are NaN, it typically means:

1. **API/LLM Errors**: The OpenAI API calls during evaluation failed silently
   - Check API key validity and rate limits
   - Verify API key has access to the required models
   - Check API quotas/usage limits

2. **Evaluation Errors**: Ragas couldn't compute metrics due to:
   - Empty or invalid contexts
   - Malformed responses or ground truth
   - Metric calculation failures

3. **Deprecated API Usage**: The warnings show Ragas is using deprecated LangChain LLM interfaces
   - This might cause issues with newer Ragas versions
   - Consider updating Ragas or using recommended LLM interfaces

## Debug Output Interpretation

From the debug output:
```
DataFrame columns: ['user_input', 'retrieved_contexts', 'response', 'reference', 
                    'faithfulness', 'answer_relevancy', 'context_precision', 'context_recall']
```

This shows:
- ✅ Dataset was accepted and converted correctly
- ✅ All required columns are present
- ❌ All metric columns are NaN (count=0.0, mean=NaN)

## What Needs to Be Done

### Option 1: Fix the Evaluation (Recommended)

The evaluation needs to actually compute metrics. To debug:

1. **Check API Key**: Ensure `OPENAI_API_KEY` is valid and has quota
   ```bash
   echo $OPENAI_API_KEY
   ```

2. **Check Ragas Logs**: Look for error messages in the test output (after the deprecation warnings)

3. **Test with Simpler Dataset**: Try evaluating with a single, simple question-answer pair to isolate the issue

4. **Update Ragas**: The deprecation warnings suggest using newer Ragas LLM interfaces
   ```bash
   pip install --upgrade ragas
   ```

### Option 2: Make Test More Lenient (Temporary)

If you want the test to pass even with NaN metrics (for CI/CD purposes), you could:

1. **Skip when metrics are NaN**: The test already does this with a helpful message
2. **Accept NaN as "evaluation not available"**: Modify thresholds to accept NaN as a valid "skip" condition
3. **Mock the evaluation**: For unit tests, mock Ragas to return valid metrics

### Option 3: Use Different Evaluation Approach

Instead of relying on Ragas's automatic evaluation:

1. **Manual metric calculation**: Compute metrics yourself using Ragas metric functions directly
2. **Use Ragas callbacks**: Integrate with Langfuse to track evaluation results
3. **Separate evaluation script**: Run evaluation outside of pytest for better debugging

## Next Steps

1. **Run the test** with verbose output to see Ragas error messages:
   ```bash
   RUN_RAG_TESTS=1 pytest tests/evaluation/test_rag_quality.py -v -s 2>&1 | grep -i "error\|exception\|failed"
   ```

2. **Check Ragas version compatibility**:
   ```bash
   pip show ragas
   ```

3. **Try a minimal evaluation**:
   ```python
   from ragas import evaluate
   from ragas.metrics import faithfulness
   from datasets import Dataset
   
   data = Dataset.from_dict({
       "question": ["Test question"],
       "ground_truth": ["Test answer"],
       "contexts": [["Test context"]],
       "answer": ["Test answer"]
   })
   
   result = evaluate(data, metrics=[faithfulness])
   print(result)
   ```

## Expected Behavior When Fixed

When the evaluation works correctly, you should see:
- Metrics with values between 0.0 and 1.0
- Test passes if metrics exceed thresholds (faithfulness > 0.90, etc.)
- Metrics printed in the test output

## Current Test Behavior

The test correctly:
- ✅ Skips when metrics are NaN (prevents false positives)
- ✅ Provides helpful error messages
- ✅ Shows debug output for diagnosis
- ✅ Handles all Ragas result formats

The test **cannot pass** until Ragas successfully computes metrics (no NaN values).


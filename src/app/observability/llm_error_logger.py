"""LLM Error Logger - Captures raw LLM responses when errors occur.

This module provides comprehensive error logging for LLM interactions,
saving raw responses to files in the artifacts directory for human review.

Features:
- Captures raw model responses (streaming and non-streaming)
- Saves to clearly labeled JSON files in artifacts/llm_errors/
- Includes full context: prompts, responses, error details, timing
- Thread-safe for parallel processing
"""

from __future__ import annotations

import json
import logging
import os
import threading
from datetime import datetime
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# Thread lock for safe file writing
_file_lock = threading.Lock()


class LLMErrorLogger:
    """Captures and saves LLM error details for debugging."""
    
    def __init__(self, artifacts_dir: Path | str | None = None) -> None:
        """Initialize the error logger.
        
        Args:
            artifacts_dir: Base artifacts directory. If None, uses artifacts/llm_errors
        """
        if artifacts_dir is None:
            # Default to project artifacts directory
            base_dir = Path(__file__).resolve().parents[3]
            artifacts_dir = base_dir / "artifacts"
        
        self.artifacts_dir = Path(artifacts_dir)
        self.errors_dir = self.artifacts_dir / "llm_errors"
        
        # Ensure directory exists
        self.errors_dir.mkdir(parents=True, exist_ok=True)
    
    def log_parsing_error(
        self,
        *,
        document_id: str,
        page_number: int,
        error_type: str,
        error_message: str,
        raw_response: str | None = None,
        accumulated_stream: str | None = None,
        prompt_messages: list[dict[str, Any]] | None = None,
        llm_config: dict[str, Any] | None = None,
        pixmap_path: str | None = None,
        timing_info: dict[str, float] | None = None,
        extra_context: dict[str, Any] | None = None,
    ) -> Path:
        """Log a parsing error with full context.
        
        Args:
            document_id: Document being processed
            page_number: Page number being parsed
            error_type: Type of error (validation_error, json_invalid, streaming_exception, etc.)
            error_message: Human-readable error message
            raw_response: Raw response from LLM (for non-streaming)
            accumulated_stream: Accumulated content from streaming (for streaming errors)
            prompt_messages: Messages sent to the LLM
            llm_config: LLM configuration (model, temperature, etc.)
            pixmap_path: Path to the page image
            timing_info: Timing information (start_time, first_token_time, etc.)
            extra_context: Any additional context
            
        Returns:
            Path to the saved error log file
        """
        timestamp = datetime.now()
        timestamp_str = timestamp.strftime("%Y%m%d_%H%M%S_%f")
        
        # Create descriptive filename
        filename = f"error_{timestamp_str}_doc_{document_id[:8]}_page_{page_number}.json"
        filepath = self.errors_dir / filename
        
        # Build error record
        error_record = {
            "metadata": {
                "timestamp": timestamp.isoformat(),
                "document_id": document_id,
                "page_number": page_number,
                "error_type": error_type,
                "pixmap_path": pixmap_path,
            },
            "error": {
                "type": error_type,
                "message": error_message,
            },
            "llm_config": llm_config or {},
            "timing": timing_info or {},
            "raw_response": {
                "content": raw_response or accumulated_stream,
                "length": len(raw_response or accumulated_stream or ""),
                "was_streaming": accumulated_stream is not None,
            },
            "prompt_messages": self._sanitize_messages(prompt_messages) if prompt_messages else None,
            "extra_context": extra_context or {},
        }
        
        # Add response analysis
        response_content = raw_response or accumulated_stream or ""
        if response_content:
            error_record["response_analysis"] = self._analyze_response(response_content)
        
        # Write to file (thread-safe)
        with _file_lock:
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(error_record, f, indent=2, ensure_ascii=False, default=str)
        
        # Log error summary to console
        logger.warning(
            "📝 LLM error logged to: %s (doc=%s, page=%s, error=%s)",
            filepath.name,
            document_id[:8],
            page_number,
            error_type,
        )
        
        # Also log the raw response to console for immediate visibility
        response_content = raw_response or accumulated_stream or ""
        if response_content:
            # Truncate for console but show enough to diagnose
            truncated = response_content[:2000]
            if len(response_content) > 2000:
                truncated += f"\n\n... [TRUNCATED - full response in {filepath.name}] ..."
            
            logger.error(
                "❌ LLM ERROR for doc=%s page=%s\n"
                "   Error: %s\n"
                "   Message: %s\n"
                "   Response length: %d chars\n"
                "   Raw response:\n%s",
                document_id[:8],
                page_number,
                error_type,
                error_message[:200],
                len(response_content),
                truncated,
            )
        
        # Also create a human-readable summary file
        summary_filepath = filepath.with_suffix(".txt")
        self._write_human_readable_summary(summary_filepath, error_record, response_content)
        
        return filepath
    
    def _sanitize_messages(self, messages: list[dict[str, Any]]) -> list[dict[str, Any]]:
        """Sanitize messages for logging (truncate large base64 images)."""
        sanitized = []
        for msg in messages:
            msg_copy = dict(msg)
            content = msg_copy.get("content")
            
            if isinstance(content, list):
                # Multi-modal content
                sanitized_content = []
                for part in content:
                    if isinstance(part, dict):
                        part_copy = dict(part)
                        # Truncate image data
                        if part_copy.get("type") == "image_url":
                            img_url = part_copy.get("image_url", {})
                            if isinstance(img_url, dict) and "url" in img_url:
                                url = img_url["url"]
                                if url.startswith("data:") and len(url) > 200:
                                    # Truncate base64 data
                                    comma_idx = url.find(",")
                                    if comma_idx > 0:
                                        header = url[:comma_idx + 1]
                                        data = url[comma_idx + 1:]
                                        img_url["url"] = f"{header}[BASE64_DATA_TRUNCATED: {len(data)} chars]"
                                        img_url["original_length"] = len(data)
                        sanitized_content.append(part_copy)
                    else:
                        sanitized_content.append(part)
                msg_copy["content"] = sanitized_content
            elif isinstance(content, str) and len(content) > 10000:
                # Truncate very long text content
                msg_copy["content"] = content[:5000] + f"\n\n[TRUNCATED: {len(content)} total chars]\n\n" + content[-2000:]
            
            sanitized.append(msg_copy)
        return sanitized
    
    def _analyze_response(self, content: str) -> dict[str, Any]:
        """Analyze the response content for common issues."""
        analysis = {
            "total_length": len(content),
            "line_count": content.count("\n") + 1,
        }
        
        # Check for truncation indicators
        if content.endswith(("...", "…")):
            analysis["possible_truncation"] = True
        
        # Check for incomplete JSON
        open_braces = content.count("{")
        close_braces = content.count("}")
        open_brackets = content.count("[")
        close_brackets = content.count("]")
        
        analysis["json_balance"] = {
            "open_braces": open_braces,
            "close_braces": close_braces,
            "open_brackets": open_brackets,
            "close_brackets": close_brackets,
            "balanced": open_braces == close_braces and open_brackets == close_brackets,
        }
        
        # Check for incomplete strings (odd number of unescaped quotes)
        # This is a rough heuristic
        quote_count = content.count('"') - content.count('\\"')
        analysis["quote_count"] = quote_count
        analysis["quotes_balanced"] = quote_count % 2 == 0
        
        # Find where the content might have been cut off
        if not analysis["json_balance"]["balanced"] or not analysis["quotes_balanced"]:
            # Find the last complete line
            lines = content.split("\n")
            for i, line in enumerate(reversed(lines)):
                if line.strip():
                    analysis["last_non_empty_line"] = {
                        "line_number": len(lines) - i,
                        "content": line[:200] + ("..." if len(line) > 200 else ""),
                    }
                    break
        
        # Check for repetition patterns
        if len(content) > 200:
            last_200 = content[-200:]
            char_counts = {}
            for c in last_200:
                char_counts[c] = char_counts.get(c, 0) + 1
            most_common = max(char_counts.items(), key=lambda x: x[1])
            analysis["last_200_most_common_char"] = {
                "char": repr(most_common[0]),
                "count": most_common[1],
                "percentage": most_common[1] / 200 * 100,
            }
        
        return analysis
    
    def _write_human_readable_summary(
        self,
        filepath: Path,
        error_record: dict[str, Any],
        raw_content: str,
    ) -> None:
        """Write a human-readable summary of the error."""
        with _file_lock:
            with open(filepath, "w", encoding="utf-8") as f:
                f.write("=" * 80 + "\n")
                f.write("LLM ERROR DEBUG LOG\n")
                f.write("=" * 80 + "\n\n")
                
                # Metadata
                meta = error_record.get("metadata", {})
                f.write(f"Timestamp:    {meta.get('timestamp', 'N/A')}\n")
                f.write(f"Document ID:  {meta.get('document_id', 'N/A')}\n")
                f.write(f"Page Number:  {meta.get('page_number', 'N/A')}\n")
                f.write(f"Error Type:   {meta.get('error_type', 'N/A')}\n")
                f.write(f"Pixmap Path:  {meta.get('pixmap_path', 'N/A')}\n")
                f.write("\n")
                
                # Error details
                error = error_record.get("error", {})
                f.write("-" * 80 + "\n")
                f.write("ERROR DETAILS\n")
                f.write("-" * 80 + "\n")
                f.write(f"{error.get('message', 'No error message')}\n\n")
                
                # LLM Config
                llm_config = error_record.get("llm_config", {})
                if llm_config:
                    f.write("-" * 80 + "\n")
                    f.write("LLM CONFIGURATION\n")
                    f.write("-" * 80 + "\n")
                    for key, value in llm_config.items():
                        f.write(f"  {key}: {value}\n")
                    f.write("\n")
                
                # Timing
                timing = error_record.get("timing", {})
                if timing:
                    f.write("-" * 80 + "\n")
                    f.write("TIMING INFO\n")
                    f.write("-" * 80 + "\n")
                    for key, value in timing.items():
                        f.write(f"  {key}: {value}\n")
                    f.write("\n")
                
                # Response analysis
                analysis = error_record.get("response_analysis", {})
                if analysis:
                    f.write("-" * 80 + "\n")
                    f.write("RESPONSE ANALYSIS\n")
                    f.write("-" * 80 + "\n")
                    f.write(f"Total Length:      {analysis.get('total_length', 'N/A')} chars\n")
                    f.write(f"Line Count:        {analysis.get('line_count', 'N/A')}\n")
                    
                    json_bal = analysis.get("json_balance", {})
                    f.write(f"JSON Balanced:     {json_bal.get('balanced', 'N/A')}\n")
                    f.write(f"  Open Braces:     {json_bal.get('open_braces', 0)}\n")
                    f.write(f"  Close Braces:    {json_bal.get('close_braces', 0)}\n")
                    f.write(f"  Open Brackets:   {json_bal.get('open_brackets', 0)}\n")
                    f.write(f"  Close Brackets:  {json_bal.get('close_brackets', 0)}\n")
                    f.write(f"Quotes Balanced:   {analysis.get('quotes_balanced', 'N/A')}\n")
                    
                    if "last_non_empty_line" in analysis:
                        last_line = analysis["last_non_empty_line"]
                        f.write(f"\nLast Non-Empty Line (#{last_line.get('line_number', '?')}):\n")
                        f.write(f"  {last_line.get('content', 'N/A')}\n")
                    
                    if "last_200_most_common_char" in analysis:
                        common = analysis["last_200_most_common_char"]
                        f.write(f"\nLast 200 chars most common: {common.get('char', 'N/A')} ")
                        f.write(f"({common.get('count', 0)} times, {common.get('percentage', 0):.1f}%)\n")
                    f.write("\n")
                
                # Raw response
                f.write("=" * 80 + "\n")
                f.write("RAW LLM RESPONSE\n")
                f.write("=" * 80 + "\n\n")
                f.write(raw_content or "[NO RESPONSE CONTENT]")
                f.write("\n\n")
                f.write("=" * 80 + "\n")
                f.write("END OF ERROR LOG\n")
                f.write("=" * 80 + "\n")


# Global instance for convenience
_default_logger: LLMErrorLogger | None = None


def get_llm_error_logger() -> LLMErrorLogger:
    """Get the default LLM error logger instance."""
    global _default_logger
    if _default_logger is None:
        _default_logger = LLMErrorLogger()
    return _default_logger


def log_llm_parsing_error(
    *,
    document_id: str,
    page_number: int,
    error_type: str,
    error_message: str,
    raw_response: str | None = None,
    accumulated_stream: str | None = None,
    prompt_messages: list[dict[str, Any]] | None = None,
    llm_config: dict[str, Any] | None = None,
    pixmap_path: str | None = None,
    timing_info: dict[str, float] | None = None,
    extra_context: dict[str, Any] | None = None,
) -> Path:
    """Convenience function to log an LLM parsing error.
    
    See LLMErrorLogger.log_parsing_error() for details.
    """
    return get_llm_error_logger().log_parsing_error(
        document_id=document_id,
        page_number=page_number,
        error_type=error_type,
        error_message=error_message,
        raw_response=raw_response,
        accumulated_stream=accumulated_stream,
        prompt_messages=prompt_messages,
        llm_config=llm_config,
        pixmap_path=pixmap_path,
        timing_info=timing_info,
        extra_context=extra_context,
    )


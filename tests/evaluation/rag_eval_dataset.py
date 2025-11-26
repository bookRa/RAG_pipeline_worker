"""RAG evaluation dataset for quality metrics using Ragas.

This module provides a dataset of question/answer pairs for evaluating RAG pipeline quality.
The dataset format follows Ragas requirements:
- question: User query
- ground_truth: Expected answer
- contexts: Retrieved chunks (list of strings)
- answer: Generated response
"""

from __future__ import annotations

from typing import Any

try:
    from datasets import Dataset
    DATASETS_AVAILABLE = True
except ImportError:
    DATASETS_AVAILABLE = False
    # Define a placeholder Dataset class if datasets is not available
    class Dataset:
        """Placeholder Dataset class when datasets package is not installed."""
        @staticmethod
        def from_dict(data: dict[str, Any]) -> Any:
            """Placeholder method."""
            return data


def load_eval_dataset() -> Dataset | dict[str, Any]:
    """Load the RAG evaluation dataset.
    
    Returns:
        Dataset with columns: question, ground_truth, contexts, answer
    """
    if not DATASETS_AVAILABLE:
        # Return dict if datasets is not available
        return {
            "question": [],
            "ground_truth": [],
            "contexts": [],
            "answer": [],
        }
    
    # Ragas expects specific column names. Based on the debug output, Ragas converts to:
    # user_input, retrieved_contexts, response, reference
    # So we'll use the standard Ragas format
    eval_data = {
        "question": [
            "What is the NAVEDTRA number for the Blueprint Reading course?",
            "Who should be contacted for content issues in the training manual?",
            "What is the purpose of the Nonresident Training Course?",
            "What organization published the Blueprint Reading manual?",
            "What is the publication date of the Blueprint Reading manual?",
        ],
        "ground_truth": [
            "NAVEDTRA 14040A",
            "Surface Warfare Officers School Command (SWOS) at (757) 444-5332",
            "To provide training materials for sailors who cannot attend resident training",
            "Naval Education and Training Professional Development and Technology Center (NETPDTC)",
            "September 2015",
        ],
        "contexts": [
            # Contexts for question 1
            [
                "Blueprint Reading and Sketching\nNAVEDTRA 14040A",
                "September 2015\nBlueprint Reading and Sketching",
            ],
            # Contexts for question 2
            [
                "For content issues, contact the servicing Center of Excellence: Surface Warfare Officers School Command (SWOS) at (757) 444-5332 or DSN 564-5332.",
            ],
            # Contexts for question 3
            [
                "Nonresident Training Courses (NRTCs) are designed for sailors who cannot attend resident training programs.",
            ],
            # Contexts for question 4
            [
                "The Naval Education and Training Professional Development and Technology Center (NETPDTC) is responsible for publishing training materials.",
            ],
            # Contexts for question 5
            [
                "September 2015\nBlueprint Reading and Sketching",
            ],
        ],
        "answer": [
            "The NAVEDTRA number is 14040A.",
            "Contact SWOS at (757) 444-5332 for content issues.",
            "The purpose is to provide training materials for sailors who cannot attend resident training.",
            "The Naval Education and Training Professional Development and Technology Center (NETPDTC) published the manual.",
            "The publication date is September 2015.",
        ],
    }
    
    return Dataset.from_dict(eval_data)


def create_dataset_from_documents(
    documents: list[dict[str, Any]],
    questions: list[str],
    ground_truths: list[str],
) -> Dataset:
    """Create a Ragas dataset from processed documents.
    
    Args:
        documents: List of processed document dictionaries
        questions: List of questions about the documents
        ground_truths: List of ground truth answers
    
    Returns:
        Dataset formatted for Ragas evaluation
    """
    contexts_list = []
    answers_list = []
    
    # For each question, simulate retrieval and generation
    # In a real implementation, you would:
    # 1. Retrieve relevant chunks using vector search
    # 2. Generate answers using LLM with retrieved context
    
    for question, ground_truth in zip(questions, ground_truths):
        # Simulate retrieval: extract relevant chunks from documents
        # This is a placeholder - in production, use actual vector retrieval
        contexts = []
        for doc in documents:
            for page in doc.get("pages", []):
                for chunk in page.get("chunks", []):
                    chunk_text = chunk.get("cleaned_text") or chunk.get("text", "")
                    if chunk_text:
                        contexts.append(chunk_text)
        
        contexts_list.append(contexts[:3])  # Limit to top 3 contexts
        
        # Simulate generation: use ground truth as placeholder
        # In production, generate using LLM
        answers_list.append(ground_truth)
    
    return Dataset.from_dict({
        "question": questions,
        "ground_truth": ground_truths,
        "contexts": contexts_list,
        "answer": answers_list,
    })


# Example dataset for testing (only if datasets is available)
if DATASETS_AVAILABLE:
    EXAMPLE_DATASET = load_eval_dataset()
else:
    EXAMPLE_DATASET = None


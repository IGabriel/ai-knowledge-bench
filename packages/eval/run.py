"""Evaluation harness for RAG system."""
import argparse
import json
import sys
from pathlib import Path
from typing import List, Dict, Any, Tuple
from datetime import datetime
import csv

# Add project root to path
sys.path.insert(0, str(Path(__file__).parent.parent.parent))

import numpy as np
from sklearn.metrics.pairwise import cosine_similarity

from packages.core.config import get_settings
from packages.core.database import get_session_maker
from packages.core.retrieval import retrieve_chunks
from packages.core.embeddings import get_embedding_generator
from packages.core.vllm_client import get_vllm_client, build_rag_prompt
from packages.core.retrieval import build_rag_context
from packages.core.logging_config import setup_logging

logger = setup_logging("eval")


def load_golden_set(dataset_path: str) -> List[Dict[str, Any]]:
    """Load golden set from JSONL file."""
    items = []
    with open(dataset_path, 'r', encoding='utf-8') as f:
        for line in f:
            if line.strip():
                items.append(json.loads(line))
    return items


def strict_source_match(
    expected_sources: List[Dict[str, str]],
    retrieved_sources: List[Dict[str, str]]
) -> Tuple[int, int]:
    """
    Check strict source matching (document_id + source_ref).
    
    Returns:
        (hit_count, total_expected)
    """
    hits = 0
    for expected in expected_sources:
        exp_doc_id = expected["document_id"]
        exp_source_ref = expected["source_ref"]
        
        for retrieved in retrieved_sources:
            ret_doc_id = retrieved["document_id"]
            ret_source_ref = retrieved["source_ref"]
            
            if exp_doc_id == ret_doc_id and exp_source_ref == ret_source_ref:
                hits += 1
                break
    
    return hits, len(expected_sources)


def calculate_recall_at_k(
    expected_sources: List[Dict[str, str]],
    retrieved_sources: List[Dict[str, str]],
    k: int
) -> float:
    """Calculate recall@k with strict source matching."""
    if not expected_sources:
        return 0.0
    
    # Consider only top-k retrieved sources
    top_k_sources = retrieved_sources[:k]
    
    hits, total = strict_source_match(expected_sources, top_k_sources)
    return hits / total if total > 0 else 0.0


def calculate_mrr(
    expected_sources: List[Dict[str, str]],
    retrieved_sources: List[Dict[str, str]]
) -> float:
    """Calculate Mean Reciprocal Rank."""
    for rank, retrieved in enumerate(retrieved_sources, start=1):
        ret_doc_id = retrieved["document_id"]
        ret_source_ref = retrieved["source_ref"]
        
        for expected in expected_sources:
            exp_doc_id = expected["document_id"]
            exp_source_ref = expected["source_ref"]
            
            if exp_doc_id == ret_doc_id and exp_source_ref == ret_source_ref:
                return 1.0 / rank
    
    return 0.0


def evaluate_question(
    question_item: Dict[str, Any],
    chunk_profile_id: str,
    top_k: int,
    embedding_model: str,
    llm_model: str,
    db_session
) -> Dict[str, Any]:
    """
    Evaluate a single question.
    
    Returns:
        Dictionary with evaluation metrics
    """
    question_id = question_item["id"]
    question = question_item["question"]
    expected_answer = question_item["expected_answer"]
    expected_sources = question_item["expected_sources"]
    
    logger.info(f"Evaluating question {question_id}: {question[:50]}...")
    
    # Retrieve chunks
    try:
        results = retrieve_chunks(
            db=db_session,
            query=question,
            chunk_profile_id=chunk_profile_id,
            top_k=top_k,
            embedding_model=embedding_model
        )
    except Exception as e:
        logger.error(f"Error retrieving chunks for {question_id}: {e}")
        return {
            "question_id": question_id,
            "error": str(e),
            "recall_at_k": 0.0,
            "mrr": 0.0,
            "semantic_similarity": 0.0,
            "citation_hit_rate": 0.0
        }
    
    # Format retrieved sources
    retrieved_sources = [
        {
            "document_id": str(result.document_id),
            "source_ref": result.source_ref
        }
        for result in results
    ]
    
    # Calculate retrieval metrics
    recall_at_k = calculate_recall_at_k(expected_sources, retrieved_sources, top_k)
    mrr = calculate_mrr(expected_sources, retrieved_sources)
    
    # Calculate citation hit rate (at least one expected source in top-k)
    hits, total = strict_source_match(expected_sources, retrieved_sources)
    citation_hit_rate = 1.0 if hits > 0 else 0.0
    
    # Generate answer
    generated_answer = ""
    semantic_similarity = 0.0
    
    if results:
        try:
            context = build_rag_context(results)
            messages = build_rag_prompt(question, context)
            
            vllm_client = get_vllm_client()
            generated_answer = vllm_client.chat(messages, max_tokens=512, temperature=0.7)
            
            # Calculate semantic similarity
            emb_gen = get_embedding_generator()
            expected_emb = emb_gen.encode([expected_answer])[0]
            generated_emb = emb_gen.encode([generated_answer])[0]
            
            semantic_similarity = cosine_similarity(
                expected_emb.reshape(1, -1),
                generated_emb.reshape(1, -1)
            )[0][0]
        
        except Exception as e:
            logger.error(f"Error generating answer for {question_id}: {e}")
            generated_answer = f"ERROR: {str(e)}"
    
    return {
        "question_id": question_id,
        "question": question,
        "expected_answer": expected_answer,
        "generated_answer": generated_answer,
        "expected_sources": expected_sources,
        "retrieved_sources": retrieved_sources,
        "recall_at_k": recall_at_k,
        "mrr": mrr,
        "semantic_similarity": float(semantic_similarity),
        "citation_hit_rate": citation_hit_rate,
        "num_expected_sources": len(expected_sources),
        "num_retrieved_sources": len(retrieved_sources)
    }


def run_evaluation(
    dataset_path: str,
    chunk_profile_id: str,
    top_k: int,
    embedding_model: str,
    llm_model: str,
    output_dir: str = "reports"
) -> Dict[str, Any]:
    """
    Run evaluation on golden set.
    
    Returns:
        Dictionary with aggregated metrics
    """
    logger.info(f"Loading golden set from {dataset_path}")
    golden_set = load_golden_set(dataset_path)
    
    logger.info(f"Loaded {len(golden_set)} questions")
    
    # Get database session
    SessionLocal = get_session_maker()
    db = SessionLocal()
    
    # Evaluate each question
    results = []
    for item in golden_set:
        result = evaluate_question(
            item,
            chunk_profile_id,
            top_k,
            embedding_model,
            llm_model,
            db
        )
        results.append(result)
    
    db.close()
    
    # Calculate aggregated metrics
    valid_results = [r for r in results if "error" not in r]
    
    if not valid_results:
        logger.error("No valid results")
        return {}
    
    avg_recall = np.mean([r["recall_at_k"] for r in valid_results])
    avg_mrr = np.mean([r["mrr"] for r in valid_results])
    avg_semantic_sim = np.mean([r["semantic_similarity"] for r in valid_results])
    citation_hit_rate = np.mean([r["citation_hit_rate"] for r in valid_results])
    
    # Calculate semantic correct rate (using threshold)
    settings = get_settings()
    threshold = settings.eval_semantic_similarity_threshold
    semantic_correct_rate = np.mean([
        1.0 if r["semantic_similarity"] >= threshold else 0.0
        for r in valid_results
    ])
    
    # Calculate embedding coverage (should be close to 1.0)
    total_expected_sources = sum([r["num_expected_sources"] for r in valid_results])
    total_retrieved_sources = sum([
        min(r["num_retrieved_sources"], top_k) for r in valid_results
    ])
    embedding_coverage = total_retrieved_sources / (len(valid_results) * top_k) if len(valid_results) > 0 else 0.0
    
    # Calculate composite score (weighted)
    # Weights: recall 30%, MRR 20%, semantic_sim 30%, citation_hit 20%
    composite_score = (
        0.30 * avg_recall +
        0.20 * avg_mrr +
        0.30 * avg_semantic_sim +
        0.20 * citation_hit_rate
    )
    
    metrics = {
        "dataset": dataset_path,
        "chunk_profile_id": chunk_profile_id,
        "embedding_model": embedding_model,
        "llm_model": llm_model,
        "top_k": top_k,
        "num_questions": len(golden_set),
        "num_valid_results": len(valid_results),
        "embedding_coverage": embedding_coverage,
        "avg_recall_at_k": avg_recall,
        "avg_mrr": avg_mrr,
        "avg_semantic_similarity": avg_semantic_sim,
        "semantic_correct_rate": semantic_correct_rate,
        "citation_hit_rate": citation_hit_rate,
        "composite_score": composite_score,
        "timestamp": datetime.utcnow().isoformat()
    }
    
    # Save results
    Path(output_dir).mkdir(parents=True, exist_ok=True)
    
    timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
    
    # Save JSON report
    json_path = Path(output_dir) / f"eval_report_{timestamp}.json"
    with open(json_path, 'w') as f:
        json.dump({
            "metrics": metrics,
            "results": results
        }, f, indent=2)
    logger.info(f"Saved JSON report to {json_path}")
    
    # Save CSV report
    csv_path = Path(output_dir) / f"eval_report_{timestamp}.csv"
    with open(csv_path, 'w', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=[
            "question_id", "recall_at_k", "mrr", "semantic_similarity",
            "citation_hit_rate", "num_expected_sources", "num_retrieved_sources"
        ])
        writer.writeheader()
        for r in valid_results:
            writer.writerow({
                "question_id": r["question_id"],
                "recall_at_k": r["recall_at_k"],
                "mrr": r["mrr"],
                "semantic_similarity": r["semantic_similarity"],
                "citation_hit_rate": r["citation_hit_rate"],
                "num_expected_sources": r["num_expected_sources"],
                "num_retrieved_sources": r["num_retrieved_sources"]
            })
    logger.info(f"Saved CSV report to {csv_path}")
    
    # Print summary
    print("\n" + "="*80)
    print("EVALUATION SUMMARY")
    print("="*80)
    print(f"Dataset: {dataset_path}")
    print(f"Questions: {len(golden_set)} ({len(valid_results)} valid)")
    print(f"Top-K: {top_k}")
    print(f"Embedding Model: {embedding_model}")
    print(f"LLM Model: {llm_model}")
    print("-"*80)
    print(f"Embedding Coverage:        {embedding_coverage:.3f} (should be close to 1.0)")
    if embedding_coverage < 0.99:
        print("  ⚠️  WARNING: Low embedding coverage detected!")
    print(f"Avg Recall@{top_k}:              {avg_recall:.3f}")
    print(f"Avg MRR:                   {avg_mrr:.3f}")
    print(f"Avg Semantic Similarity:   {avg_semantic_sim:.3f}")
    print(f"Semantic Correct Rate:     {semantic_correct_rate:.3f} (threshold={threshold})")
    print(f"Citation Hit Rate:         {citation_hit_rate:.3f}")
    print(f"Composite Score:           {composite_score:.3f}")
    print("="*80)
    print(f"\nReports saved to: {output_dir}/")
    
    return metrics


def main():
    """Main entry point for evaluation CLI."""
    parser = argparse.ArgumentParser(description="Run evaluation on golden set")
    parser.add_argument("--dataset", required=True, help="Path to golden set JSONL file")
    parser.add_argument("--profile", required=True, help="Chunk profile ID")
    parser.add_argument("--topk", type=int, default=5, help="Top-K for retrieval")
    parser.add_argument("--embedding", default=None, help="Embedding model name")
    parser.add_argument("--llm", default=None, help="LLM model name")
    parser.add_argument("--output", default="reports", help="Output directory for reports")
    
    args = parser.parse_args()
    
    settings = get_settings()
    embedding_model = args.embedding or settings.embedding_model
    llm_model = args.llm or settings.vllm_model
    
    metrics = run_evaluation(
        dataset_path=args.dataset,
        chunk_profile_id=args.profile,
        top_k=args.topk,
        embedding_model=embedding_model,
        llm_model=llm_model,
        output_dir=args.output
    )


if __name__ == "__main__":
    main()

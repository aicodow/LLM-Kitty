"""Pipeline sub-package — five-rail evaluation orchestrator.

The pipeline manages the full lifecycle of an evaluation run:

    Input Rail    → Configuration validation and concurrency setup
    Retrieval Rail → Provider resolution and instantiation
    Dialog Rail   → Test case construction and expansion
    Execution Rail → Concurrency-gated provider invocation with assertions
    Output Rail   → Result aggregation, statistics, and provider shutdown
"""

from kitty.pipeline.evaluator import EvaluationPipeline, evaluate

__all__ = [
    "EvaluationPipeline",
    "evaluate",
]

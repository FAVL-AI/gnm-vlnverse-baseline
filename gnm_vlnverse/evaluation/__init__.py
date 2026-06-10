"""Evaluation utilities for the GNM-VLNVerse baseline.

This package initialiser is intentionally lightweight so metrics can be used
in proof/demo environments without PyTorch.

The full evaluator (requires torch and Isaac Sim) must be imported explicitly:
    from gnm_vlnverse.evaluation.evaluator import GNMEvaluator
"""

from .metrics import NavigationMetrics, compute_all_metrics

__all__ = ["NavigationMetrics", "compute_all_metrics"]

"""Data utilities for the GNM-VLNVerse baseline.

This package initialiser is intentionally lightweight so converter utilities
can be used in proof/demo environments without PyTorch.

Training datasets and augmentation require torch and must be imported explicitly:
    from gnm_vlnverse.data.dataset import GNMDataset, collate_gnm
    from gnm_vlnverse.data.augmentation import GNMAugmentation
"""

from .vlntube_converter import VLNTubeConverter, ConversionStats

__all__ = [
    "VLNTubeConverter",
    "ConversionStats",
]

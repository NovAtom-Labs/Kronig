"""Canonical simulator-independent scientific results."""

from tcad_agent.results.catalog import (
    DatasetCatalogEntry,
    ResultViewKind,
    build_dataset_catalog,
)
from tcad_agent.results.datasets import Dataset, ScientificAxis
from tcad_agent.results.models import CanonicalResult
from tcad_agent.results.query import DatasetQueryError, DatasetQueryResult, query_dataset

__all__ = [
    "CanonicalResult",
    "Dataset",
    "DatasetCatalogEntry",
    "DatasetQueryError",
    "DatasetQueryResult",
    "ResultViewKind",
    "ScientificAxis",
    "build_dataset_catalog",
    "query_dataset",
]

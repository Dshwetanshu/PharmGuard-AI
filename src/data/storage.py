"""Persistence helpers.

Transparently reads/writes parquet when pyarrow is available, CSV otherwise.
Lets the pipeline run in minimal environments while keeping parquet in prod.
"""
from __future__ import annotations

from pathlib import Path

import pandas as pd

try:
    import pyarrow  # noqa: F401
    _HAS_PARQUET = True
except ImportError:
    _HAS_PARQUET = False


def _sibling_csv(path: Path) -> Path:
    return path.with_suffix(".csv")


def write_table(df: pd.DataFrame, path: Path) -> Path:
    """Write a DataFrame. Uses parquet if available, CSV fallback otherwise.

    Returns the actual path written.
    """
    path = Path(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    if _HAS_PARQUET and path.suffix == ".parquet":
        df.to_parquet(path, index=False)
        return path
    csv_path = _sibling_csv(path)
    df.to_csv(csv_path, index=False)
    return csv_path


def read_table(path: Path) -> pd.DataFrame:
    """Read a DataFrame, tolerating parquet-vs-CSV divergence."""
    path = Path(path)
    if path.exists() and path.suffix == ".parquet" and _HAS_PARQUET:
        return pd.read_parquet(path)
    csv = _sibling_csv(path)
    if csv.exists():
        return pd.read_csv(csv)
    if path.exists():
        # Fall back to pandas' auto-detection
        return pd.read_csv(path)
    raise FileNotFoundError(f"Neither {path} nor {csv} exists.")


def table_exists(path: Path) -> bool:
    path = Path(path)
    return path.exists() or _sibling_csv(path).exists()

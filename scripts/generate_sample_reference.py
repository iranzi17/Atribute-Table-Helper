#!/usr/bin/env python3
"""Utility to build a demo reference workbook without tracking binaries."""
from __future__ import annotations

from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
REFERENCE_DIR = PROJECT_ROOT / "reference_data"
OUTPUT_PATH = REFERENCE_DIR / "sample_substations.xlsx"


def build_sample_dataframe() -> pd.DataFrame:
    """Create a tiny mock dataset that mirrors the expected schema."""

    return pd.DataFrame(
        [
            {
                "station_id": "RW-001",
                "station_name": "Kigali North",
                "voltage_kv": 110,
                "commissioned": "2018-05-01",
                "status": "Active",
            },
            {
                "station_id": "RW-002",
                "station_name": "Nyabarongo",
                "voltage_kv": 220,
                "commissioned": "2019-08-12",
                "status": "Maintenance",
            },
            {
                "station_id": "RW-003",
                "station_name": "Gisenyi East",
                "voltage_kv": 110,
                "commissioned": "2020-11-20",
                "status": "Active",
            },
        ]
    )


def main() -> None:
    REFERENCE_DIR.mkdir(exist_ok=True)
    df = build_sample_dataframe()

    with pd.ExcelWriter(OUTPUT_PATH, engine="openpyxl") as writer:
        df.to_excel(writer, index=False, sheet_name="substations")

    print(f"Sample workbook created at {OUTPUT_PATH}")


if __name__ == "__main__":
    main()

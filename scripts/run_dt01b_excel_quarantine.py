"""
CLI Runner for Scenario `DT-01b` (Prong 2 Multi-Tab Excel Catalog Dynamic Profiler,
RML Mapping Generator & Row-Level `pySHACL` Quarantine Gate).

Usage:
    python scripts/run_dt01b_excel_quarantine.py
"""

from __future__ import annotations

import argparse
from pathlib import Path
import sys

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config_loader import load_config
from src.logger import setup_logger
from src.track_b.s2_excel_shacl_ingestor import run_dt01b_excel_quarantine


def parse_args() -> argparse.Namespace:
    """Parse CLI arguments for Scenario `DT-01b`."""
    parser = argparse.ArgumentParser(
        description=(
            "Scenario DT-01b: Prong 2 Excel Catalog Dynamic Profiler, "
            "RML Mapping Generator & Row-Level pySHACL Quarantine Gate"
        )
    )
    return parser.parse_args()


def main() -> int:
    """Execute Scenario `DT-01b` and print audit metrics."""
    _ = parse_args()
    config = load_config()
    logger = setup_logger(config)
    result = run_dt01b_excel_quarantine(config=config, logger=logger)

    print(
        f"DT-01b COMPLETE | Target Sheet: {result.target_sheet_name} | "
        f"Excluded Distractor Tabs: {result.excluded_distractor_tabs_count} | "
        f"Valid B2B SKUs Loaded: {result.valid_skus_loaded_count} | "
        f"pySHACL Quarantined Rows: {result.quarantined_rows_count} | "
        f"Catalog Triples: {result.catalog_triples_materialized} | "
        f"Virtual IB Triples: {result.virtual_ib_triples_count}"
    )
    print(f"RML Mapping : {result.rml_mapping_path}")
    print(f"TriG Store  : {result.trig_dataset_path}")
    print(f"Report HTML : {result.quarantine_html_report_path}")
    print(f"Report MD   : {result.quarantine_markdown_report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())


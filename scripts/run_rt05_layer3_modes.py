r"""
Scenario RT-05 CLI Runner: Layer 3 NL2Semantics Dual Shadow Comparison & MCP Check.

Usage:
  .\.venv\Scripts\python.exe scripts\run_rt05_layer3_modes.py --mode dual_comparison --circuit-id CIR-994821
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

WORKSPACE_ROOT = Path(__file__).resolve().parent.parent
if str(WORKSPACE_ROOT) not in sys.path:
    sys.path.insert(0, str(WORKSPACE_ROOT))

from src.config import load_config
from src.layer3.template_compiler import compile_stored_sparql_templates
from src.logger import setup_logger
from src.mcp_servers.semantic_read_mcp import execute_query_knowledge_fabric


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Run Scenario RT-05 Layer 3 NL2Semantics modes."
    )
    parser.add_argument(
        "--mode",
        choices=["dual_comparison", "voicebox_hybrid", "zero_shot_llm", "all"],
        default="dual_comparison",
        help="Layer 3 execution mode to run (default: dual_comparison).",
    )
    parser.add_argument(
        "--circuit-id",
        default="CIR-994821",
        help="Target circuit ID (default: CIR-994821).",
    )
    parser.add_argument(
        "--intent",
        default=(
            "Retrieve the complete federated service assurance context for circuit {circuit_id}, "
            "including customer identity, ER legal entity match, catalog packet loss SLA and "
            "auto-remediation flag, hardware optical Rx/LOS thresholds, and MSA SLA policy."
        ),
        help="Natural-language intent passed to Layer 3.",
    )
    parser.add_argument(
        "--compile-templates",
        action="store_true",
        help="Compile data/semantic_store/stored_sparql_templates.yaml dynamically before running.",
    )
    args = parser.parse_args()

    config = load_config(WORKSPACE_ROOT / "config.yaml")
    logger = setup_logger(config, "run_rt05_layer3_modes", WORKSPACE_ROOT)

    if args.compile_templates:
        compile_res = compile_stored_sparql_templates(
            config=config,
            logger=logger,
            root_dir=WORKSPACE_ROOT,
            test_circuit_id=args.circuit_id,
        )
        print(
            f"Compiled {len(compile_res.template_ids)} SPARQL templates -> "
            f"{compile_res.output_path} (verified rows={compile_res.layer4_verified_rows})"
        )

    intent = args.intent.format(circuit_id=args.circuit_id)
    modes = (
        ["dual_comparison", "voicebox_hybrid", "zero_shot_llm"]
        if args.mode == "all"
        else [args.mode]
    )

    for mode in modes:
        logger.info("Running Scenario RT-05 (mode=%s, circuit=%s)", mode, args.circuit_id)
        output = execute_query_knowledge_fabric(
            natural_language_intent=intent,
            target_circuit_id=args.circuit_id,
            execution_mode=mode,
            obo_jwt=None,
            config=config,
            logger=logger,
            root_dir=WORKSPACE_ROOT,
        )
        res = output["layer3_result"]
        print(f"=== RT-05 Mode: {mode} ===")
        print(f"Auth Mode: {output['auth_metadata']['auth_mode']}")
        print(f"Model Used: {res['model_used']}")
        print(f"On-Disk virtual:ib Triples After: {res['disk_virtual_ib_triples_after']}")
        if res.get("voicebox_result"):
            vb = res["voicebox_result"]
            print(
                f"Voicebox Hybrid: template={vb['template_id']} | ast_passed={vb['ast_audit']['passed']} | "
                f"rows={vb['row_count']} | latency_ms={vb['latency_ms']}"
            )
        if res.get("zero_shot_result"):
            zs = res["zero_shot_result"]
            print(
                f"Zero-Shot Shadow: ast_passed={zs['ast_audit']['passed']} | "
                f"rows={zs['row_count']} | latency_ms={zs['latency_ms']} | "
                f"missing_fields={len(zs['missing_fields'])} | error={zs['execution_error']}"
            )
        print(f"Comparison Report HTML: {res['report_html_path']}")
        print(f"Comparison Report MD:   {res['report_markdown_path']}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

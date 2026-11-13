# Step 9 (`IMP-011`) Layer 2 Assurance Specialist Execution Report (`RT-01` .. `RT-03`)

- **Generated At (UTC):** `2026-11-13T14:42:06Z`
- **Scenarios Executed:** `RT-01, RT-02, RT-03`
- **CQRS State Reset After Run:** `True`

## 1. Branch Execution Summary

| Scenario | Preset | Selected Branch | TMF640 Calls | Blocking Guardrails | TMF621 Ticket | SHACL Conforms |
| :--- | :--- | :--- | :---: | :--- | :--- | :---: |
| `RT-01` | `branch_a_soft_degradation` | `BRANCH_A_SOFT_OPTICAL_DEGRADATION` | `1` | `NONE` | `TT-621-0001 (MINOR / RESOLVED_AUTO)` | `True` |
| `RT-02` | `branch_b_hard_fiber_cut` | `BRANCH_B_HARD_FIBER_CUT` | `0` | `GR-INV-01` | `TT-621-0002 (CRITICAL / OPEN_DISPATCHED)` | `True` |
| `RT-03` | `branch_c_maintenance_lock` | `BRANCH_C_MAINTENANCE_LOCK` | `0` | `GR-INV-02` | `TT-621-0003 (WARNING / DEFERRED_MAINTENANCE)` | `True` |

## Scenario `RT-01` (`branch_a_soft_degradation`)
- **LLM Model:** `gemini-3.8-flash`
- **LLM Proposed Branch / Recalibration:** `BRANCH_A_SOFT_OPTICAL_DEGRADATION` / `True`
- **Pre-Execution Guardrails:** `remediation_allowed=True`, `blocking=[]`
- **Grounded Root-Cause Summary:** Circuit CIR-994821 serving customer A Corporate Enterprise under SLA policy CIR-994821 Bespoke SLA & Optical Recalibration Policy (product SKU ETH-10G-GOLD) exhibited soft optical degradation. Live un-cached gNMI telemetry on OLT port OLT04-P12 measured optical Rx power at -26.1 dBm (above the -27.5 dBm critical LOS cutoff threshold), Tx power at -1.2 dBm, and packet loss at 0.45%. With maintenance lock confirmed false and no active CRQ, execution qualified under Branch A guardrails for autonomous closed-loop optical DDM recalibration.

| Step # | Step ID | Catalog Primitive URI | Concrete MCP Tool | Status | Detail |
| :---: | :--- | :--- | :--- | :--- | :--- |
| `1` | `STEP_1_SEMANTIC_CONTEXT` | `mcp://semantic-read/query_knowledge_fabric` | `semantic_read_mcp.query_knowledge_fabric` | `COMPLETED` | Retrieved 6-graph context for CIR-994821 (OLT04-P12, ETH-10G-GOLD). |
| `2` | `STEP_2_SINGLETON_OPTICAL_PROBE` | `cqrs://singleton-check/probe_resource_state` | `gnmi_telemetry_mcp.probe_optical_ddm_telemetry` | `COMPLETED` | Rx=-26.1 dBm, loss=0.45%, lock=False. |
| `3` | `STEP_3_GUARDRAIL_BRANCH_EXECUTION` | `cqrs://transactional-write/execute_governed_mutation` | `tmf640_activation_mcp.recalibrate_optical_ddm_bias` | `EXECUTED` | Executed TMF640 optical DDM bias recalibration ACT-640-0001 on CIR-994821 (OLT04-P12 -> CPE-ASN-7741); Rx power restored from -26.1 dBm to -21.4 dBm. |
| `4` | `STEP_4_POST_VERIFICATION_COMMIT` | `cqrs://transactional-write/commit_validated_graph_triples` | `gnmi_telemetry_mcp.probe_optical_ddm_telemetry` | `VERIFIED_GR_POST_01` | Post-check Rx=-21.4 dBm, loss=0.01%. |
| `4` | `STEP_4_POST_VERIFICATION_COMMIT` | `cqrs://transactional-write/commit_validated_graph_triples` | `tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket` | `CREATED` | CREATED TMF621 TroubleTicket TT-621-0001 (MINOR / RESOLVED_AUTO) for circuit CIR-994821 and resource OLT04-P12; pySHACL conforms=True. |

## Scenario `RT-02` (`branch_b_hard_fiber_cut`)
- **LLM Model:** `gemini-3.8-flash`
- **LLM Proposed Branch / Recalibration:** `BRANCH_B_HARD_FIBER_CUT` / `False`
- **Pre-Execution Guardrails:** `remediation_allowed=False`, `blocking=['GR-INV-01']`
- **Grounded Root-Cause Summary:** Circuit CIR-994821 for customer A Corporate Enterprise (SLA tier ETH-10G-GOLD) exhibits critical optical loss of signal with Rx power at -38.5 dBm (breaching the -27.5 dBm hardware LOS threshold), Tx power at -1.1 dBm, and 99.8% packet loss. Telemetry confirms maintenance_lock is false with no active CRQ. Guardrail GR-INV-01 blocks autonomous DDM recalibration, enforcing Branch B physical field dispatch.

| Step # | Step ID | Catalog Primitive URI | Concrete MCP Tool | Status | Detail |
| :---: | :--- | :--- | :--- | :--- | :--- |
| `1` | `STEP_1_SEMANTIC_CONTEXT` | `mcp://semantic-read/query_knowledge_fabric` | `semantic_read_mcp.query_knowledge_fabric` | `COMPLETED` | Retrieved 6-graph context for CIR-994821 (OLT04-P12, ETH-10G-GOLD). |
| `2` | `STEP_2_SINGLETON_OPTICAL_PROBE` | `cqrs://singleton-check/probe_resource_state` | `gnmi_telemetry_mcp.probe_optical_ddm_telemetry` | `COMPLETED` | Rx=-38.5 dBm, loss=99.8%, lock=False. |
| `3` | `STEP_3_GUARDRAIL_BRANCH_EXECUTION` | `cqrs://transactional-write/execute_governed_mutation` | `tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket` | `CREATED` | GR-INV-01 blocked TMF640 (0 invocations); CREATED TMF621 TroubleTicket TT-621-0002 (CRITICAL / OPEN_DISPATCHED) for circuit CIR-994821 and resource OLT04-P12; pySHACL conforms=True. |
| `4` | `STEP_4_POST_VERIFICATION_COMMIT` | `cqrs://transactional-write/commit_validated_graph_triples` | `tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket` | `COMMITTED_NO_REMEDIATION` | Branch BRANCH_B_HARD_FIBER_CUT completed with 0 TMF640 calls; ticket TT-621-0002 pySHACL-verified. |

## Scenario `RT-03` (`branch_c_maintenance_lock`)
- **LLM Model:** `gemini-3.8-flash`
- **LLM Proposed Branch / Recalibration:** `BRANCH_C_MAINTENANCE_LOCK` / `False`
- **Pre-Execution Guardrails:** `remediation_allowed=False`, `blocking=['GR-INV-02']`
- **Grounded Root-Cause Summary:** Circuit CIR-994821 assigned to customer A Corporate Enterprise (CUST-ENT-409) under SLA tier ETH-10G-GOLD exhibited optical Rx power of -26.1 dBm and Tx power of -1.2 dBm with 0.45% packet loss on OLT port OLT04-P12. While optical levels fall within the soft degradation window, live gNMI telemetry confirmed an active maintenance lock (maintenance_lock == true) associated with change request MAINT-CRQ-88210. Under guardrail GR-INV-02 and Branch C routing, automated DDM recalibration is suppressed to prevent race conditions during active maintenance.

| Step # | Step ID | Catalog Primitive URI | Concrete MCP Tool | Status | Detail |
| :---: | :--- | :--- | :--- | :--- | :--- |
| `1` | `STEP_1_SEMANTIC_CONTEXT` | `mcp://semantic-read/query_knowledge_fabric` | `semantic_read_mcp.query_knowledge_fabric` | `COMPLETED` | Retrieved 6-graph context for CIR-994821 (OLT04-P12, ETH-10G-GOLD). |
| `2` | `STEP_2_SINGLETON_OPTICAL_PROBE` | `cqrs://singleton-check/probe_resource_state` | `gnmi_telemetry_mcp.probe_optical_ddm_telemetry` | `COMPLETED` | Rx=-26.1 dBm, loss=0.45%, lock=True. |
| `3` | `STEP_3_GUARDRAIL_BRANCH_EXECUTION` | `cqrs://transactional-write/execute_governed_mutation` | `tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket` | `CREATED` | GR-INV-02 blocked TMF640 (0 invocations); CREATED TMF621 TroubleTicket TT-621-0003 (WARNING / DEFERRED_MAINTENANCE) for circuit CIR-994821 and resource OLT04-P12; pySHACL conforms=True. |
| `4` | `STEP_4_POST_VERIFICATION_COMMIT` | `cqrs://transactional-write/commit_validated_graph_triples` | `tmf621_trouble_ticket_mcp.create_or_update_trouble_ticket` | `COMMITTED_NO_REMEDIATION` | Branch BRANCH_C_MAINTENANCE_LOCK completed with 0 TMF640 calls; ticket TT-621-0003 pySHACL-verified. |

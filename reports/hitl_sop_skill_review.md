# HITL Gate 3 — SOP-to-Skill & Adverse Guardrail Review (`VERIFIED_LOCKED`)

- **Generated At (UTC):** `2026-11-13T12:22:25Z`
- **Model Used:** `gemini-3.8-flash`
- **Status:** `VERIFIED_LOCKED`
- **Target Skill:** `telco.assurance.l2_fiber_degradation` (`SOP-ASSUR-402`, eTOM `1.3.7, 1.4.5`)
- **DT-02b Adverse Guardrail Tests:** `3/3` passed

## 1. Procedure Scope & Distractor Pruning

| Section | Procedure ID | Score | Disposition | Rationale |
|---|---|---:|---|---|
| Section 1: Purpose, General NOC Safety & Change Control Governance | `GOV-NOC-001` | 0.60 | `GOVERNANCE_CONTEXT` | Provides overarching NOC safety invariants, OBO token authentication requirements, and CI/CD SOP slicing rules across all assurance domains. |
| Section 2 (SOP-ASSUR-101): BGP Peering Session Flap Triage & Dampening | `SOP-ASSUR-101` | 0.05 | `OUT_OF_SCOPE_PRUNED` | IP Core routing and eBGP route flap dampening procedure; out of scope for L2 enterprise optical access assurance. |
| Section 3 (SOP-ASSUR-205): 5G RAN gNodeB Sector Outage & Tilt Reset | `SOP-ASSUR-205` | 0.05 | `OUT_OF_SCOPE_PRUNED` | Mobile 5G RAN antenna electrical tilt and fronthaul procedure; unrelated to fixed enterprise Carrier Ethernet L2 circuits. |
| Section 4 (SOP-ASSUR-310): Residential GPON ONT Optical Dying-Gasp Handling | `SOP-ASSUR-310` | 0.15 | `OUT_OF_SCOPE_PRUNED` | Consumer mass GPON ONT power failure handling; incompatible with SLA-governed dedicated B2B enterprise fiber circuits. |
| Section 5 (SOP-ASSUR-402 — TARGET): Enterprise L2 Fiber Packet-Loss Triage & Optical DDM Recalibration | `SOP-ASSUR-402` | 1.00 | `IN_SCOPE_SELECTED` | Directly implements UC-001 enterprise L2 circuit packet-loss triage, optical DDM telemetry diagnosis, and governed remediation. |
| Section 6 (SOP-ASSUR-509): Core DWDM Erbium-Doped Fiber Amplifier (EDFA) Pump Laser Replacement | `SOP-ASSUR-509` | 0.10 | `OUT_OF_SCOPE_PRUNED` | Core DWDM optical line amplifier maintenance procedure; irrelevant to access/aggregation L2 Carrier Ethernet demarcation. |

## 2. Machine-Enforceable Guardrails (`guardrails_sop_402.json`)

| Guardrail ID | Phase | Parameter | Operator | Threshold | Target Tool |
|---|---|---|---|---|---|
| `GR-PRE-01` | `PRE_CONDITION` | `gnmi_uncached_probed` | `==` | `True` | `TMF640_SERVICE_ACTIVATION` |
| `GR-INV-01` | `EXECUTION_INVARIANT` | `rx_power_dbm` | `>=` | `-27.5` | `TMF640_SERVICE_ACTIVATION` |
| `GR-INV-02` | `EXECUTION_INVARIANT` | `maintenance_lock` | `==` | `False` | `TMF640_SERVICE_ACTIVATION` |
| `GR-POST-01` | `POST_CONDITION` | `post_check_required` | `==` | `True` | `TMF640_SERVICE_ACTIVATION` |

## 3. DT-02b Adverse Guardrail Rejection Proof

| Test ID | Scenario | Expected Guardrail | Actual Blocked | Actual Guardrail | Passed |
|---|---|---|---|---|---|
| `ADV-01` | Critical LOS Hard Fiber Cut Bypass Attempt | `GR-INV-01` | `True` | `GR-INV-01` | `True` |
| `ADV-02` | Active Maintenance Window Lock Bypass Attempt | `GR-INV-02` | `True` | `GR-INV-02` | `True` |
| `ADV-03` | Stale / Un-Probed Telemetry Cache Bypass Attempt | `GR-PRE-01` | `True` | `GR-PRE-01` | `True` |

## 4. HITL Gate 3 NOC Architect Verification Questions

1. Does the pruning of distractor runbooks (SOP-ASSUR-101, 205, 310, 509) correctly isolate SOP-ASSUR-402 as the sole in-scope operational procedure for UC-001?
2. Does the compiled 4-step state machine correctly bind read-plane SPARQL federation and write-plane CQRS primitives strictly adhering to Option 2.1D-Catalog?
3. Are the machine-enforceable guardrail threshold parameters (-27.5 dBm LOS cutoff, maintenance lock, and mandatory pre/post checks) properly configured for vendor hardware model NOK-7210-SAS-Mxp?
4. Do the specified guardrail invariants provide deterministic 3/3 adverse scenario interception proof against cached telemetry, severe physical fiber breaks, and active maintenance windows?

# MASTER NOC ASSURANCE STANDARD OPERATING PROCEDURES RUNBOOK (v2026.4)

**Document ID:** `SOP-NOC-MASTER-RUNBOOK-2026-V4`  
**Custodian:** Enterprise Network Operations & Transport Engineering  
**Contained Procedures:** `SOP-ASSUR-101`, `SOP-ASSUR-205`, `SOP-ASSUR-310`, `SOP-ASSUR-402` (TARGET UC-001), `SOP-ASSUR-509`

---

## Section 1: Purpose, General NOC Safety & Change Control Governance
- **Procedure / Governance ID:** `GOV-NOC-001`
- **TM Forum eTOM Alignment:** eTOM 1.3 / 1.4 Cross-Domain Assurance Governance

1.1 Purpose: This Master Network Operations Center (NOC) Assurance Runbook consolidates five (5) standard operating procedures across IP Core, 5G RAN, Residential GPON, Enterprise L2 Carrier Ethernet, and DWDM Optical Transport.

1.2 Agentic & Human Safety Invariants: No automated worker agent or NOC engineer may execute a state mutation against production network elements without (a) verifying an active OAuth2 On-Behalf-Of (OBO) security token, (b) executing a live non-cached singleton hardware pre-check, (c) acquiring a short-lived Redis mutex resource lock, and (d) validating post-action knowledge writes against SHACL shapes.

1.3 Scope Slicing Rule for SOP-to-Skill Compilation: When compiling a domain-specific Worker Agent skill, the SOP-to-Skill CI/CD pipeline must slice ONLY the target SOP section matching the requested procedure ID and discard unrelated sections.

---

## Section 2 (SOP-ASSUR-101): BGP Peering Session Flap Triage & Dampening
- **Procedure / Governance ID:** `SOP-ASSUR-101`
- **TM Forum eTOM Alignment:** eTOM 1.4.5 IP Core Routing Trouble Management (DISTRACTOR PROCEDURE)

2.1 Trigger Condition: eBGP peering session experiences >= 5 state transitions (Established <-> Idle) within a 10-minute sliding window on core autonomous system border routers (ASBRs).

2.2 Diagnostic Steps: Query NetFlow/BMP collector for prefix churn; verify IXP LAN ARP reachability; apply RFC 7196 route flap dampening profile (half-life=15m, suppress=2000, reuse=750, max-suppress=60m).

2.3 Remediation Action: Invoke core BGP dampening RPC if peer is non-transit; otherwise escalate to Tier-3 IP Core Engineering.

---

## Section 3 (SOP-ASSUR-205): 5G RAN gNodeB Sector Outage & Tilt Reset
- **Procedure / Governance ID:** `SOP-ASSUR-205`
- **TM Forum eTOM Alignment:** eTOM 1.4.5 Mobile Radio Access Network Assurance (DISTRACTOR PROCEDURE)

3.1 Trigger Condition: 3GPP n78 (3.5 GHz) gNodeB sector reports VSWR > 1.8 or complete RRC connection drop across > 50 active UEs.

3.2 Diagnostic Steps: Check AISG v2.0 Remote Electrical Tilt (RET) actuator current draw and CPRI/eCPRI fronthaul optical link status.

3.3 Remediation Action: If RET motor calibration fault is isolated, execute non-intrusive AISG tilt actuator soft reset; if VSWR > 2.2, lock RF carrier and dispatch tower rigger.

---

## Section 4 (SOP-ASSUR-310): Residential GPON ONT Optical Dying-Gasp Handling
- **Procedure / Governance ID:** `SOP-ASSUR-310`
- **TM Forum eTOM Alignment:** eTOM 1.3.7 Consumer FTTx Mass Assurance (DISTRACTOR PROCEDURE)

4.1 Trigger Condition: Residential GPON ONT emits PLOAM Dying-Gasp message followed by OLT PON port LOSi alarm.

4.2 Diagnostic Steps: Correlate across neighboring ONTs on the same 1:32 passive optical splitter; if < 3 ONTs affected and Dying-Gasp flag is true, classify as customer premises power outage.

4.3 Remediation Action: Suppress field dispatch for 4 hours and send automated SMS power-check notification to residential subscriber.

---

## Section 5 (SOP-ASSUR-402 — TARGET): Enterprise L2 Fiber Packet-Loss Triage & Optical DDM Recalibration
- **Procedure / Governance ID:** `SOP-ASSUR-402`
- **TM Forum eTOM Alignment:** eTOM 1.3.7 Problem Handling & 1.4.5 Resource Trouble Management (TARGET USE CASE UC-001)

5.1 Procedure Metadata: SOP ID: SOP-ASSUR-402 | Revision: 4.1 | Target Skill ID: telco.assurance.l2_fiber_degradation | Approved By: Lead Transport Architect (j.vandijk@telco-arch.nl).

5.2 Pre-Condition Gate (Guardrail GR-PRE-01): Verify that reported_packet_loss_pct >= 0.5%. If reported_packet_loss_pct < 0.5%, immediately abort the troubleshooting workflow and return status NO_ACTION_REQUIRED without querying downstream systems or mutating network state.

5.3 Step 1 — Multi-Pronged Semantic Context Lookup (STEP_1_SEMANTIC_CONTEXT): Invoke the Semantic Knowledge Layer (Layer 3/4 read-only SPARQL federation) for the target circuit_id (e.g., CIR-994821) to join:

  - Prong 1 (Virtual SQL CMDB <urn:telco:graph:virtual:ib>): Customer identity (CUST-ENT-409 / 'A Corporate Enterprise'), active CustomerFacingService (CIR-994821), linked ServiceSpecification (ETH-10G-GOLD), terminating OLT port (OLT04-P12), PE router (NLD-HAG-PE02), CPE asset (CPE-ASN-7741), and CPE hardware model SKU (NOK-7210-SAS-Mxp).

  - Prong 2 (Materialized Excel Catalog <urn:telco:graph:ref:catalog>): ServiceSpecification SLA max packet loss threshold (0.1% for ETH-10G-GOLD), auto-remediation flag (YES), and eligible upgrade SKU (ETH-100G-PLATINUM).

  - Prong 3 (BITES PDF Graphs <urn:telco:graph:bites:doc-hw-v4> & <urn:telco:graph:bites:doc-msa-v1>): Vendor optical transceiver operating ranges for NOK-7210-SAS-Mxp (normal Rx: -14.0 dBm to -24.9 dBm; DDM recalibration window: -25.0 dBm to -27.5 dBm; critical LOS cutoff: < -27.5 dBm) and MSA Annex B bespoke SLA penalty (15% monthly service credit if loss > 0.1% for >30m) + pre-authorized DDM recalibration clause.

5.4 Step 2 — Real-Time Singleton Optical Probe & Mutex Lock (STEP_2_SINGLETON_OPTICAL_PROBE): Invoke probe_live_optical_port on the CQRS Singleton Check MCP Server with bypass_cache=true for the terminating port (OLT04-P12 / CPE-ASN-7741). Retrieve instantaneous live optical Rx power (live_rx_dbm), verify maintenance window status (maintenance_lock), and acquire a short-lived Redis port mutex lock token (singleton_lock_token).

5.5 Step 3 & Step 4 — Deterministic 3-Way Branching & Guardrail Enforcement:

  * Branch A (Soft Optical Degradation — Target Happy Path): IF reported_packet_loss_pct >= 0.5% AND live_rx_dbm is between -25.0 dBm and the hardware manual's minimum Rx threshold (-27.5 dBm for NOK-7210-SAS-Mxp, i.e., -27.5 <= live_rx_dbm <= -25.0) AND maintenance_lock == false:

      1) Enforce Guardrail GR-INV-01 (verify maintenance_lock == false and active singleton_lock_token).

      2) Invoke execute_tmf640_recalibration on the CQRS Transactional Write MCP Server to perform non-intrusive DDM optical transceiver AGC/bias recalibration.

      3) Invoke record_verified_incident_resolution on the CQRS Transactional Write MCP Server to commit a pySHACL-validated TroubleTicket resolution triple into <urn:telco:graph:assurance:resolutions>.

  * Branch B (Hard Fiber Cut / Severe Attenuation): IF reported_packet_loss_pct >= 0.5% AND live_rx_dbm is strictly below the hardware minimum (< -27.5 dBm):

      1) Enforce Execution Invariant Guardrail GR-INV-02: STRICTLY FORBID all remote write/recalibration tools (execute_tmf640_recalibration).

      2) Invoke create_tmf621_field_dispatch on the CQRS Transactional Write MCP Server to dispatch a field fiber splicing/OTDR technician crew.

  * Branch C (Active Maintenance Freeze / Normal Optical Power / Low Loss): IF reported_packet_loss_pct < 0.5% OR maintenance_lock == true OR live_rx_dbm > -25.0 dBm:

      1) Enforce Execution Invariant Guardrail GR-INV-01: Abort all remote network mutations.

      2) Release the Redis port mutex lock and log a non-intrusive monitoring diagnostic note.

---

## Section 6 (SOP-ASSUR-509): Core DWDM Erbium-Doped Fiber Amplifier (EDFA) Pump Laser Replacement
- **Procedure / Governance ID:** `SOP-ASSUR-509`
- **TM Forum eTOM Alignment:** eTOM 1.4.5 Optical Transport Core Maintenance (DISTRACTOR PROCEDURE)

6.1 Trigger Condition: Core DWDM line amplifier raises Pump-Laser-Bias-Current-High (> 950 mA) or Optical-Gain-Tilt alarm on 80-channel C-band span.

6.2 Diagnostic Steps: Verify ROADM optical protection switching status on diverse path; confirm zero single-homed wavelengths on degraded EDFA degree.

6.3 Remediation Action: Shift C-band optical multiplex section (OMS) traffic to protection fiber via GMPLS control plane and schedule planned chassis line-card swap.

---

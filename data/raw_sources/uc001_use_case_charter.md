# Use Case Charter — `UC-001`: Enterprise L2 Fiber Packet-Loss Triage & Automated Optical DDM Recalibration

- **Use Case ID:** `UC-001`
- **Target Domain:** Enterprise B2B Assurance & Optical Access Network Operations
- **TM Forum eTOM (GB921) Process Scope:**
  - `1.3.7` — **Problem Handling** (Customer Problem Reception, SLA Triage, Root-Cause Correlation & Customer Notification)
  - `1.4.5` — **Resource Trouble Management** (Network Fault Localization, Optical Transceiver DDM Diagnostics, Autonomous Self-Healing & Field Dispatch)

---

## 1. Business Problem & Operational Objective

Enterprise customers subscribing to high-availability Layer 2 Carrier Ethernet circuits (`ETH-10G-GOLD`, `ETH-100G-PLATINUM`, `ETH-1G-SILVER`, `MPLS-VPN-STD`, `SDWAN-PRO`) require sub-minute SLA triage and automated remediation when frame/packet loss exceeds their contracted SLA threshold.

Specifically, for VIP enterprise subscribers (such as **A Corporate Enterprise** / **A Corporate Enterprise B.V.**, customer ID `CUST-ENT-409`, registration `NL-8841209`) operating active L2 fiber circuit `CIR-994821` (`ETH-10G-GOLD`), the autonomous assurance agent must:
1. **Resolve Active Subscribed Inventory & Commercial SLA Entitlements**:
   - Traverse the enterprise customer party record, the currently active Customer-Facing Service (CFS) circuit record (filtering out any superseded historical SCD Type 2 service upgrades/downgrades where the validity window has closed), the commercial Service Specification catalog tier (packet-loss ceiling, availability target, autonomous remediation eligibility, and recommended upgrade SKU), and any custom Master Service Agreement (MSA) penalty clauses.
   - Normalize legacy numeric operational status codes (`10` = `ACTIVE`, `20` = `MAINTENANCE`, `99` = `DECOMMISSIONED`) and mixed bandwidth units (`Kbps`, `Mbps`, `Gbps`) into canonical Gigabits per second (`Gbps`).
2. **Resolve Underlying Network Bearer & Physical Hardware Topology**:
   - Traverse from the active CFS circuit to its realizing Resource-Facing Service (RFS) bearer, the aggregating Provider Edge (PE) router (`NLD-HAG-PE02`), the terminating Optical Line Terminal (OLT) port (`OLT04-P12`), the physical outside-plant fiber span, the Customer Premises Equipment (CPE) demarcation device (`CPE-ASN-7741`), and its vendor hardware model specification (`NOK-7210-SAS-Mxp`) and optical DDM calibration profile.
3. **Execute Closed-Loop Assurance Diagnosis & Governed Action**:
   - Probe live gNMI optical telemetry on the OLT port (`rx_optical_power_dbm`, `tx_optical_power_dbm`, `laser_bias_current_ma`, `transceiver_temp_c`).
   - Compare live Rx optical power against the vendor hardware manual DDM envelope:
     - **Soft Attenuation Degradation** (Rx power between `-24.0 dBm` and `-27.9 dBm`): Execute autonomous TMF640 optical laser bias recalibration if permitted by the commercial SLA tier (`autoRemediationAllowed = true`).
     - **Hard Physical Fiber Cut / LOS** (Rx power $\le -28.0\text{ dBm}$): Dispatch a TMF621 field fiber splicing trouble ticket and commit a SHACL-validated `tmf:TroubleTicket` record to the knowledge graph.
     - **Planned Maintenance Window** (`MAINTENANCE`): Suppress false-positive alarms and field dispatches.

---

## 2. Explicit Scope Boundaries & Out-of-Scope Domains

- **In Scope (Assurance, Service Inventory & Network Topology):**
  - Enterprise Customer identity, segment tier, and account ownership.
  - Active Customer-Facing Service (CFS) circuits, operational status, normalized bandwidth (`Gbps`), and commercial Service Specification links.
  - Resource-Facing Service (RFS) bearers, PE routers, OLT optical ports, CPE demarcation devices, VLAN tags, fiber spans, hardware model specifications, optical DDM calibration profiles, SLA clauses, and TMF621 trouble tickets.
- **Out of Scope (Financial ERP, Billing & Internal Database Plumbing):**
  - Financial invoice ledgers, tax codes, VAT percentages, general ledger posting dates, dunning levels, and ERP batch/audit hash tables must be **strictly excluded** as out-of-scope noise (`EXCLUDED_NOISE`).
  - Internal database surrogate keys, legacy CRM foreign keys, legacy billing tags, row creation timestamps, and NMS polling sync watermarks must be **excluded** from the Conceptual TBox so zero physical database plumbing leaks into the semantic ontology.
  - Physical SCD Type 2 temporal control columns (`CFS_ROW_ID`, `VALID_FROM_TS`, `VALID_TO_TS`) must be used **strictly** inside the R2RML SQL pushdown filter (`WHERE VALID_TO_TS IS NULL`) and never exposed as Conceptual TBox properties.


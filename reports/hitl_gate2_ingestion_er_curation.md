# Scenario DT-01c: HITL Gate 2 PDF BITES, Quarantine Disposition & Fuzzy ER Curation

- **Gate 2 Status:** `PROMOTED (HITL Gate 2 Approved)`
- **Generated At (UTC):** `2026-11-13T07:44:50Z`
- **Model Used:** `gemini-3.8-flash`
- **Active PDFs Analyzed:** `2`
- **Fuzzy ER Matches Proposed:** `3`

## 1. Review & Disposition of `pySHACL`-Quarantined Excel Rows (DT-01b)

Quarantined rows on disk: `2` (Recommended Disposition: `KEEP_QUARANTINED (Excluded from Catalog)`).

| Excel Row | SKU Code | Disposition | Violated Constraint(s) |
|---:|---|---|---|
| 24 | `DARK-FIBER-METRO-X` | `KEEP_QUARANTINED (Excluded from Catalog)` | `http://www.w3.org/ns/shacl#MinInclusiveConstraintComponent; http://www.w3.org/ns/shacl#DatatypeConstraintComponent; http://www.w3.org/ns/shacl#InConstraintComponent` |
| 25 | `SDWAN-LEGACY-99` | `KEEP_QUARANTINED (Excluded from Catalog)` | `http://www.w3.org/ns/shacl#MaxInclusiveConstraintComponent; http://www.w3.org/ns/shacl#DatatypeConstraintComponent; http://www.w3.org/ns/shacl#InConstraintComponent` |

## 2. PDF Page Relevance Filtering & Scoped BITES Triples

### `MSA_Contract_A_Corporate_Enterprise_2026.pdf` (`DOCUMENT_SCOPE` -> `<urn:telco:graph:bites:doc-msa-v1>`)
- **Version:** `MSA-2026-NL-409` | **SHA-256:** `d29a054c385fd1c2...` | **Lifecycle:** `ACTIVE`
- **Relevant Pages (2):** 3, 4
- **Excluded Distractor Pages (2):** 1, 2
- **Extracted BITES Triples:** `8`

### `Vendor_Optical_Hardware_Manual_v4.pdf` (`GLOBAL_SCOPE` -> `<urn:telco:graph:bites:doc-hw-v4>`)
- **Version:** `REV 4.0` | **SHA-256:** `57b8d5fe3a3d2191...` | **Lifecycle:** `ACTIVE`
- **Relevant Pages (2):** 4, 5
- **Excluded Distractor Pages (3):** 1, 2, 3
- **Extracted BITES Triples:** `16`

## 3. Fuzzy Entity Resolution Curation Queue (`rapidfuzz`)

| Source PDF | PDF Mention | Canonical CMDB Customer | Raw Sim | Norm Sim | Composite | Status | Proposed Bridge |
|---|---|---|---:|---:|---:|---|---|
| `MSA_Contract_A_Corporate_Enterprise_2026.pdf` | `A Corporate Enterprise B.V.` | `A Corporate Enterprise` (`CUST-ENT-409`) | 0.8980 | 1.0000 | **0.9235** | `CURATION_PENDING` | `owl:sameAs, skos:exactMatch, telco:resolvedToCanonicalCustomer` |
| `MSA_Contract_A_Corporate_Enterprise_2026.pdf` | `A Corporate Enterprise B.V.` | `A Corporate Enterprise` (`CUST-ENT-409`) | 0.8980 | 1.0000 | **0.9235** | `CURATION_PENDING` | `owl:sameAs, skos:exactMatch, telco:resolvedToCanonicalCustomer` |
| `MSA_Contract_A_Corporate_Enterprise_2026.pdf` | `A Corporate Enterprise B.V.` | `A Corporate Enterprise` (`CUST-ENT-409`) | 0.8980 | 1.0000 | **0.9235** | `CURATION_PENDING` | `owl:sameAs, skos:exactMatch, telco:resolvedToCanonicalCustomer` |

## 4. HITL Gate 2 Steward / Architect Verification Questions

1. Does the Steward confirm the exclusion or re-mapping of any pySHACL-quarantined catalog product rows from Prong 2 prior to establishing downstream joins with customer contract SLA clauses?
2. Does the Architect approve the scope partitioning assigning Vendor_Optical_Hardware_Manual_v4.pdf to GLOBAL_SCOPE (graph: <urn:telco:graph:bites:doc-hw-v4>) and MSA_Contract_A_Corporate_Enterprise_2026.pdf to DOCUMENT_SCOPE (graph: <urn:telco:graph:bites:doc-msa-v1>), along with the distractor exclusions of electrical, thermal, and liability pages?
3. Does the Data Steward validate the fuzzy Entity Resolution linking proposal bridging extracted customer mention 'A Corporate Enterprise B.V.' (registration NL-8841209) to canonical CMDB subject <urn:telco:party:customer:CUST-ENT-409> ('A Corporate Enterprise')?
4. Does the Telecom Architect sign off on the automated closed-loop DDM recalibration window boundary (-25.0 dBm to -27.5 dBm) and the requirement for synchronous un-cached gNMI probing and maintenance_lock verification before autonomous TMF640 execution on circuit CIR-994821?

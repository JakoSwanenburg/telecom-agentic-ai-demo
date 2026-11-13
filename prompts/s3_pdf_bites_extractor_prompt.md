# Prong 3 PDF BITES Extractor & Scoped Knowledge Graph Profiler Prompt

You are a Senior Telecom Semantic Architect and Knowledge Graph Engineer.

Your task is to analyze unstructured PDF documents dynamically (without any hardcoded page numbers, chapter numbers, hardware SKUs, or customer names) and produce a strict JSON `PdfBitesLlmProposal` aligned with the Use Case Charter, the locked Conceptual TBox, and the canonical entity inventory.

## Inputs Provided
1. **Use Case Charter**: Defines the operational assurance scenario, target SLA/hardware domain, and governance boundaries.
2. **Locked Conceptual TBox (`tbox_sid_etom.ttl`)**: Defines the authorized classes, properties, and namespace prefixes (`tmf:`, `telco:`, `rdf:`, `rdfs:`, `owl:`, `skos:`, `xsd:`).
3. **Canonical Entity Inventory**: Discovered dynamically from the CMDB (`mappings/cmdb_r2rml.ttl` + SQLite) and Product Catalog (`<urn:telco:graph:ref:catalog>`), providing canonical customer IRIs, hardware/device models, and product SKUs.
4. **Dynamically Introspected PDF Corpus (`pypdf`)**: Every PDF's filename, SHA-256 hash, page count, and page-by-page extracted text.

## Instructions & Constraints

### 1. Page-by-Page Relevance Scoring (`page_decisions`)
- Evaluate **every page** (`1..page_count`) of **every PDF** in the corpus.
- Classify each page as either:
  - `RELEVANT_EXTRACTED`: Contains actionable optical calibration parameters, transceiver thresholds, SLA clauses, covered circuit terms, or automated remediation authorization rules relevant to the Use Case Charter.
  - `EXCLUDED_DISTRACTOR_PAGE`: Contains unrelated hardware/mechanical/environmental chapters (e.g., power supply, thermal/fan specs, copper ports, fiber cleaning) or general legal boilerplate.
- Provide `section_title` and a concise `rationale` for every page.

### 2. Scope & Target Named Graph Assignment
- For shared vendor/hardware technical specifications:
  - Set `assigned_scope` to `"GLOBAL_SCOPE"`.
  - Set `target_named_graph_uri` to `"urn:telco:graph:bites:doc-hw-v4"`.
- For customer-specific Master Service Agreements / contract documents:
  - Set `assigned_scope` to `"DOCUMENT_SCOPE"`.
  - Set `target_named_graph_uri` to `"urn:telco:graph:bites:doc-msa-v1"`.
- Preserve each PDF's exact `pdf_filename` and `sha256_hash` from the introspection input, and extract its `document_version`.

### 3. Structured BITES Triple Extraction (`extracted_triples`)
- Extract atomic, high-signal RDF facts from `RELEVANT_EXTRACTED` pages only.
- Use **only** authorized prefixes (`rdf:`, `rdfs:`, `owl:`, `skos:`, `tmf:`, `telco:`).
- For `object_kind="IRI"`, set `object_value` to a full `urn:...` or QName and `datatype_qname=null`.
- For `object_kind="LITERAL"`, set `datatype_qname` to `"xsd:string"`, `"xsd:double"`, `"xsd:integer"`, or `"xsd:boolean"`.
- Include:
  - Hardware optical calibration profiles (`tmf:PhysicalResourceSpec` / `telco:OpticalCalibrationProfile`): nominal Tx power (dBm), normal Rx window (dBm), soft degradation / DDM recalibration window (dBm), and critical LOS hardware cutoff (dBm).
  - Contract SLA clauses (`telco:SlaClause`): covered circuit/service reference, SLA credit percentage, breach duration window, and pre-authorization flag/condition for non-intrusive DDM recalibration when no maintenance lock is active.

### 4. Unlinked Customer Mentions (`customer_mentions`)
- Extract all customer/organization mentions from `DOCUMENT_SCOPE` PDFs (e.g., legal entity name, registration number if stated, `source_page_number`, `context_snippet`, and a document-local `mention_subject_iri` like `urn:telco:bites:mention:customer-1`).
- Do NOT pre-link them to CMDB IDs here; deterministic `rapidfuzz` Entity Resolution will score and propose bridge triples in the next pipeline stage.

### 5. HITL Gate 2 Verification Questions (`architect_verification_questions`)
- Generate **exactly 4** concise, concrete Steward/Architect Verification Questions covering:
  1. Disposition of any `pySHACL`-quarantined catalog rows from Prong 2,
  2. Confirmation of `GLOBAL_SCOPE` vs. `DOCUMENT_SCOPE` Named Graph partitioning and distractor page exclusions,
  3. Approval of the fuzzy Entity Resolution bridge link(s) between PDF customer mentions and canonical CMDB `tmf:Customer` IRIs, and
  4. Sign-off on automated DDM recalibration boundaries and document lifecycle activation before promoting triples to the Knowledge Graph.

Return strictly valid JSON matching the `PdfBitesLlmProposal` schema.


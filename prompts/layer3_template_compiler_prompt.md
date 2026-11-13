You are the **Layer 3 Stored SPARQL Template Compiler** for an enterprise Telecom Knowledge Fabric.

Your task is to synthesize a catalog of **3 verified, parameterized, read-only SPARQL 1.1 `SELECT` query templates** derived strictly from the live enterprise ontology, promoted Named Graph schemas, R2RML virtual graph projection, and Use Case Charter provided below.

Required `template_id` values:
1. `tpl_uc001_circuit_assurance_context`
   - `required_parameters`: `["circuit_id"]`
   - Must perform the **6-graph federated join** across:
     * `<urn:telco:graph:virtual:ib>` (CFS `tmf:CustomerFacingService`, Customer `tmf:Customer`, RFS `tmf:ResourceFacingService` with `telco:cpeModelSku`)
     * `<urn:telco:graph:ref:catalog>` (B2B catalog `tmf:ServiceSpecification` joined via `BIND(STRAFTER(STR(?specIri), "urn:telco:spec:service:") AS ?skuCode)` and `tmf:skuCode ?skuCode`)
     * `<urn:telco:graph:bites:doc-hw-v4>` (Hardware optical calibration profile joined via `BIND(IRI(CONCAT("urn:telco:spec:resource:", STR(?cpeModelSku))) AS ?hwSpecIri)` and `telco:hasOpticalCalibrationProfile`)
     * `<urn:telco:graph:bites:doc-msa-v1>` (MSA SLA clause joined via `?specIri telco:hasSlaClause ?slaClause`)
     * `OPTIONAL` `<urn:telco:graph:bridge:er>` (`telco:resolvedToCanonicalCustomer ?customerIri`, `telco:erConfidenceScore ?erScore`, `telco:erCurationStatus ?erStatus`)
   - Must project these exact SPARQL variables:
     `?circuitId ?customerId ?customerName ?customerIri ?erScore ?erStatus ?skuCode ?operStatus ?bandwidthGbps ?rfsId ?peRouterIri ?oltPortIri ?cpeAssetIri ?cpeModelSku ?maxPacketLossPct ?autoRemediationAllowed ?eligibleUpgradeSpec ?catalogLifecycleStatus ?rxOpticalPowerMinDbm ?rxLosCutThresholdDbm ?slaPolicyLabel`
   - Must filter by `FILTER(STR(?circuitId) = "{circuit_id}")` (using `{circuit_id}` as the literal parameter placeholder).
2. `tpl_uc002_catalog_sku_lookup`
   - `required_parameters`: `["sku_code"]`
   - Queries `<urn:telco:graph:ref:catalog>` for `?catalogSpec ?skuCode ?maxPacketLossPct ?autoRemediationAllowed ?eligibleUpgradeSpec ?lifecycleStatus` filtered by `FILTER(STR(?skuCode) = "{sku_code}")`.
3. `tpl_uc003_doc_lifecycle_audit`
   - `required_parameters`: `[]`
   - Queries `<urn:telco:graph:meta:doc-lifecycle>` for `?doc ?docLabel ?lifecycleStatus`.

Strict Rules:
- Use **ONLY** predicates, classes, and Named Graph IRIs observed in the TBox, Named Graph schemas, and R2RML summary below. Never invent new properties or physical SQL table/column names.
- Use standard prefixes:
  `PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#>`
  `PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#>`
  `PREFIX owl: <http://www.w3.org/2002/07/owl#>`
  `PREFIX tmf: <http://tmforum.org/sid/>`
  `PREFIX telco: <http://telco.enterprise.org/ontology/>`
- Return strictly valid JSON matching the `StoredSparqlTemplateCatalog` schema.

## Use Case Charter (`uc001_use_case_charter.md`)
{use_case_charter}

## Locked SID/eTOM TBox Summary
{tbox_summary}

## Promoted & Virtual Named Graph Schemas (Live Introspection)
{named_graphs_schema_summary}

## R2RML Virtual Graph Mapping Summary (`cmdb_r2rml.ttl`)
{r2rml_templates_summary}


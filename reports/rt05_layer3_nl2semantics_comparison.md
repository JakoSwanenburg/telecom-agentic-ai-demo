# Scenario RT-05 — Layer 3 `NL2Semantics` Dual Shadow Comparison Report

- **Execution Mode:** `dual_comparison`
- **Model Used:** `gemini-3.8-flash`
- **Target Circuit ID:** `CIR-994821`
- **Natural Language Intent:** Retrieve the complete federated service assurance context for circuit CIR-994821, including customer identity, ER legal entity match, catalog packet loss SLA and auto-remediation flag, hardware optical Rx/LOS thresholds, and MSA SLA policy.
- **On-Disk `<urn:telco:graph:virtual:ib>` Triples After Query:** `0`

## Side-by-Side Comparison

| Dimension | Voicebox Hybrid (`Option 3C`) | Zero-Shot LLM (Shadow) |
|---|---|---|
| **AST Gatekeeper Passed** | `True` | `True` |
| **Latency (ms)** | `9681.15` | `91785.43` |
| **Rows Returned** | `1` | `3` |
| **Unknown Vocabulary URIs** | `[]` | `[]` |
| **Missing Context Fields** | `[]` | `['circuitId', 'customerId', 'customerName', 'skuCode', 'operStatus', 'bandwidthGbps', 'rfsId', 'cpeModelSku', 'maxPacketLossPct', 'autoRemediationAllowed', 'slaPolicyLabel']` |
| **Execution Error** | `None` | `None` |

## Voicebox Hybrid Selected Template: `tpl_uc001_circuit_assurance_context`

- **Parameters:** `{'circuit_id': 'CIR-994821'}`
- **Pruned TBox Classes:** `['http://telco.enterprise.org/ontology/CpeDeviceResource', 'http://telco.enterprise.org/ontology/OltPortResource', 'http://telco.enterprise.org/ontology/OpticalCalibrationProfile', 'http://telco.enterprise.org/ontology/PeRouterResource', 'http://telco.enterprise.org/ontology/SlaClause', 'http://tmforum.org/sid/Customer', 'http://tmforum.org/sid/CustomerFacingService', 'http://tmforum.org/sid/PhysicalResource', 'http://tmforum.org/sid/ResourceFacingService', 'http://tmforum.org/sid/ServiceSpecification']`

```sparql
PREFIX rdf: <http://www.w3.org/1999/02/22-rdf-syntax-ns#> PREFIX rdfs: <http://www.w3.org/2000/01/rdf-schema#> PREFIX owl: <http://www.w3.org/2002/07/owl#> PREFIX tmf: <http://tmforum.org/sid/> PREFIX telco: <http://telco.enterprise.org/ontology/> SELECT ?circuitId ?customerId ?customerName ?customerIri ?erScore ?erStatus ?skuCode ?operStatus ?bandwidthGbps ?rfsId ?peRouterIri ?oltPortIri ?cpeAssetIri ?cpeModelSku ?maxPacketLossPct ?autoRemediationAllowed ?eligibleUpgradeSpec ?catalogLifecycleStatus ?rxOpticalPowerMinDbm ?rxLosCutThresholdDbm ?slaPolicyLabel WHERE { GRAPH <urn:telco:graph:virtual:ib> { ?cfsIri a tmf:CustomerFacingService ; tmf:serviceId ?circuitId ; tmf:hasCustomer ?customerIri ; tmf:isDescribedBy ?specIri ; tmf:operationalStatus ?operStatus ; telco:bandwidthGbps ?bandwidthGbps . ?customerIri a tmf:Customer ; tmf:customerId ?customerId ; tmf:partyLegalName ?customerName . ?rfsIri a tmf:ResourceFacingService ; tmf:supportsService ?cfsIri ; tmf:rfsId ?rfsId ; telco:terminatesOnRouter ?peRouterIri ; telco:usesOltPort ?oltPortIri ; telco:demarcatesAtCpe ?cpeAssetIri ; telco:cpeModelSku ?cpeModelSku . FILTER(STR(?circuitId) = "CIR-994821") } BIND(STRAFTER(STR(?specIri), "urn:telco:spec:service:") AS ?skuCode) GRAPH <urn:telco:graph:ref:catalog> { ?catalogSpec a tmf:ServiceSpecification ; tmf:skuCode ?skuCode ; telco:maxPacketLossPct ?maxPacketLossPct ; telco:autoRemediationAllowed ?autoRemediationAllowed ; telco:eligibleUpgradeSpec ?eligibleUpgradeSpec ; telco:lifecycleStatus ?catalogLifecycleStatus . } BIND(IRI(CONCAT("urn:telco:spec:resource:", STR(?cpeModelSku))) AS ?hwSpecIri) GRAPH <urn:telco:graph:bites:doc-hw-v4> { ?hwSpecIri telco:hasOpticalCalibrationProfile ?optProfile . ?optProfile telco:rxOpticalPowerMinDbm ?rxOpticalPowerMinDbm ; telco:rxLosCutThresholdDbm ?rxLosCutThresholdDbm . } GRAPH <urn:telco:graph:bites:doc-msa-v1> { ?specIri telco:hasSlaClause ?slaClause . ?slaClause rdfs:label ?slaPolicyLabel . } OPTIONAL { GRAPH <urn:telco:graph:bridge:er> { ?erMention telco:resolvedToCanonicalCustomer ?customerIri ; telco:erConfidenceScore ?erScore ; telco:erCurationStatus ?erStatus . } } }
```

## Zero-Shot LLM Generated SPARQL (Shadow)

```sparql
PREFIX tmf: <http://tmforum.org/sid/>
PREFIX telco: <http://telco.enterprise.org/ontology/>
PREFIX owl: <http://www.w3.org/2002/07/owl#>

SELECT DISTINCT ?circuit ?serviceId ?customer ?partyLegalName ?erMatch ?serviceSpec ?maxPacketLossPct ?autoRemediationAllowed ?opticalProfile ?rxOpticalPowerMinDbm ?rxLosCutThresholdDbm ?slaClause WHERE {
  GRAPH <urn:telco:graph:virtual:ib> {
    ?circuit a tmf:CustomerFacingService ;
             tmf:serviceId "CIR-994821" ;
             tmf:hasCustomer ?customer ;
             tmf:isDescribedBy ?serviceSpec .
    
    OPTIONAL { ?circuit tmf:serviceId ?serviceId . }
    OPTIONAL { ?customer tmf:partyLegalName ?partyLegalName . }

    OPTIONAL {
      ?rfs tmf:supportsService ?circuit ;
           telco:demarcatesAtCpe ?cpe .
      ?cpe tmf:hasResourceSpecification ?resSpec .
    }
  }

  OPTIONAL {
    GRAPH <urn:telco:graph:bridge:er> {
      ?customer ?erPred ?erMatch .
    }
  }

  OPTIONAL {
    GRAPH <urn:telco:graph:ref:catalog> {
      ?serviceSpec telco:maxPacketLossPct ?maxPacketLossPct ;
                   telco:autoRemediationAllowed ?autoRemediationAllowed .
    }
  }

  OPTIONAL {
    GRAPH <urn:telco:graph:bites:doc-hw-v4> {
      ?resSpec telco:hasOpticalCalibrationProfile ?opticalProfile .
      ?opticalProfile telco:rxOpticalPowerMinDbm ?rxOpticalPowerMinDbm ;
                      telco:rxLosCutThresholdDbm ?rxLosCutThresholdDbm .
    }
  }

  OPTIONAL {
    GRAPH <urn:telco:graph:bites:doc-msa-v1> {
      ?serviceSpec telco:hasSlaClause ?slaClause .
    }
  }
}
```

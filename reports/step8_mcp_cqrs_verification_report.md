# Step 8 (`IMP-010`) Southbound MCP & CQRS Verification Report

- **Generated At (UTC):** `2026-11-13T13:33:17Z`
- **Checks Passed:** `11/11`
- **CQRS State Reset After Verification:** `True`

| Check ID | Preset | Server | Result | Detail |
| :--- | :--- | :--- | :--- | :--- |
| `CHK-A1-GNMI-PRE` | `branch_a_soft_degradation` | `gnmi_telemetry_mcp` | **PASS** | rx_dbm=-26.1, loss=0.45%, post_recal=False |
| `CHK-A2-TMF640-EXEC` | `branch_a_soft_degradation` | `tmf640_activation_mcp` | **PASS** | status=EXECUTED, activations=1 |
| `CHK-A3-GNMI-POST` | `branch_a_soft_degradation` | `gnmi_telemetry_mcp` | **PASS** | rx_dbm=-21.4, loss=0.01%, post_recal=True |
| `CHK-A4-TMF621-VALID` | `branch_a_soft_degradation` | `tmf621_trouble_ticket_mcp` | **PASS** | status=CREATED, shacl_conforms=True |
| `CHK-A5-TMF621-SHACL-REJECT` | `branch_a_soft_degradation` | `tmf621_trouble_ticket_mcp` | **PASS** | status=REJECTED_SHACL_VIOLATION, persisted=False, shacl_conforms=False |
| `CHK-B1-GNMI-LOS` | `branch_b_hard_fiber_cut` | `gnmi_telemetry_mcp` | **PASS** | rx_dbm=-38.5, loss=99.8%, los_alarm=True |
| `CHK-B2-TMF640-INTERLOCK` | `branch_b_hard_fiber_cut` | `tmf640_activation_mcp` | **PASS** | status=REJECTED_SAFETY_INTERLOCK, reason_code=LOS_CRITICAL_CUTOFF_ACTIVE |
| `CHK-B3-TMF621-P1` | `branch_b_hard_fiber_cut` | `tmf621_trouble_ticket_mcp` | **PASS** | status=CREATED, shacl_conforms=True |
| `CHK-C1-GNMI-LOCK` | `branch_c_maintenance_lock` | `gnmi_telemetry_mcp` | **PASS** | maintenance_lock=True, crq=MAINT-CRQ-88210 |
| `CHK-C2-TMF640-INTERLOCK` | `branch_c_maintenance_lock` | `tmf640_activation_mcp` | **PASS** | status=REJECTED_SAFETY_INTERLOCK, reason_code=MAINTENANCE_WINDOW_LOCK_ACTIVE |
| `CHK-C3-TMF621-DEFERRED` | `branch_c_maintenance_lock` | `tmf621_trouble_ticket_mcp` | **PASS** | status=CREATED, shacl_conforms=True |

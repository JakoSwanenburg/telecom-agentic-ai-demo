# ============================================================================
# Core Serverless Managed Infrastructure — Telecom Agentic AI Demo
# Naming pattern: <project-prefix>-<resource-type>-<purpose>
# Guaranteeing clean `terraform destroy` via force_destroy = true
# ============================================================================

resource "google_storage_bucket" "artifacts" {
  name                        = "${var.project_id}-bkt-artifacts"
  project                     = var.project_id
  location                    = var.region
  storage_class               = "STANDARD"
  force_destroy               = true
  uniform_bucket_level_access = true
  public_access_prevention    = "enforced"

  versioning {
    enabled = true
  }

  labels = {
    project     = var.project_prefix
    environment = var.environment
    use_case    = "uc-001"
    managed_by  = "terraform"
  }

  depends_on = [
    google_project_service.enabled_apis["storage.googleapis.com"]
  ]
}


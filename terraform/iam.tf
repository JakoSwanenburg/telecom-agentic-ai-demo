# ============================================================================
# Least-Privilege IAM & Dedicated Workload Service Account
# Compliant with AGENTS.md Part 5.8 (Zero primitive roles, zero exported keys)
# ============================================================================

resource "google_service_account" "runtime_sa" {
  project      = var.project_id
  account_id   = "${var.project_prefix}-sa-runtime"
  display_name = "Telecom Agentic AI Runtime Workload Service Account"
  description  = "Least-privilege service account for Layer 1-5 and CQRS MCP runtime services"

  depends_on = [
    google_project_service.enabled_apis["iam.googleapis.com"]
  ]
}

locals {
  runtime_iam_roles = toset([
    "roles/logging.logWriter",
    "roles/cloudtrace.agent",
    "roles/secretmanager.secretAccessor",
    "roles/aiplatform.user",
  ])
}

resource "google_project_iam_member" "runtime_least_privilege" {
  for_each = local.runtime_iam_roles

  project = var.project_id
  role    = each.value
  member  = "serviceAccount:${google_service_account.runtime_sa.email}"
}

resource "google_storage_bucket_iam_member" "runtime_artifacts_reader" {
  bucket = google_storage_bucket.artifacts.name
  role   = "roles/storage.objectViewer"
  member = "serviceAccount:${google_service_account.runtime_sa.email}"
}


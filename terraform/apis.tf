locals {
  required_apis = toset([
    "run.googleapis.com",
    "artifactregistry.googleapis.com",
    "secretmanager.googleapis.com",
    "logging.googleapis.com",
    "cloudtrace.googleapis.com",
    "aiplatform.googleapis.com",
    "storage.googleapis.com",
    "iam.googleapis.com",
  ])
}

resource "google_project_service" "enabled_apis" {
  for_each = local.required_apis

  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}


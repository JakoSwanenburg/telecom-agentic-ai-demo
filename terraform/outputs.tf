output "project_id" {
  description = "Active GCP Project ID"
  value       = var.project_id
}

output "region" {
  description = "Active GCP Region"
  value       = var.region
}

output "runtime_service_account_email" {
  description = "Email of the dedicated least-privilege runtime service account"
  value       = google_service_account.runtime_sa.email
}

output "artifacts_bucket_name" {
  description = "Name of the Cloud Storage bucket for semantic/SOP artifacts"
  value       = google_storage_bucket.artifacts.name
}


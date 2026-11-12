variable "project_id" {
  description = "Single isolated GCP Project ID assigned to this workspace"
  type        = string
}

variable "region" {
  description = "Default GCP region for all regional resources (Netherlands)"
  type        = string
  default     = "europe-west4"
}

variable "project_prefix" {
  description = "Prefix used in naming convention <project-prefix>-<resource-type>-<purpose>"
  type        = string
  default     = "telco-agent"
}

variable "environment" {
  description = "Deployment environment label (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "gcp_access_token" {
  description = "Optional short-lived OAuth2 access token from gcloud auth print-access-token"
  type        = string
  default     = null
  sensitive   = true
}



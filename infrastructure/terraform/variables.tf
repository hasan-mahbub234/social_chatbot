variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "us-east-1"
}

variable "app_name" {
  description = "Application name — used as prefix for all resources"
  type        = string
  default     = "ai-agent"
}

variable "environment" {
  description = "Deployment environment"
  type        = string
  default     = "prod"
  validation {
    condition     = contains(["prod", "staging", "dev"], var.environment)
    error_message = "environment must be prod, staging, or dev"
  }
}

variable "db_instance_class" {
  description = "RDS instance class"
  type        = string
  default     = "db.t3.small"
}

variable "db_password" {
  description = "RDS master password — set via TF_VAR_db_password env var"
  type        = string
  sensitive   = true
}

variable "redis_node_type" {
  description = "ElastiCache node type"
  type        = string
  default     = "cache.t3.micro"
}

variable "web_desired_count" {
  description = "Number of web ECS tasks"
  type        = number
  default     = 2
}

variable "worker_desired_count" {
  description = "Number of Celery worker ECS tasks"
  type        = number
  default     = 2
}

variable "web_cpu" {
  description = "Web task CPU units"
  type        = number
  default     = 512
}

variable "web_memory" {
  description = "Web task memory (MB)"
  type        = number
  default     = 1024
}

variable "worker_cpu" {
  description = "Worker task CPU units"
  type        = number
  default     = 1024
}

variable "worker_memory" {
  description = "Worker task memory (MB)"
  type        = number
  default     = 2048
}

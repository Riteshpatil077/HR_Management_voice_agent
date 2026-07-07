variable "aws_region" {
  description = "AWS region to deploy into"
  type        = string
  default     = "ap-south-1"
}

variable "environment" {
  description = "Deployment environment (development, staging, production)"
  type        = string
  validation {
    condition     = contains(["development", "staging", "production"], var.environment)
    error_message = "Environment must be one of: development, staging, production."
  }
}

variable "vpc_cidr" {
  description = "CIDR block for the VPC"
  type        = string
  default     = "10.0.0.0/16"
}

variable "private_subnet_cidrs" {
  description = "CIDR blocks for private subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.1.0/24", "10.0.2.0/24", "10.0.3.0/24"]
}

variable "public_subnet_cidrs" {
  description = "CIDR blocks for public subnets (one per AZ)"
  type        = list(string)
  default     = ["10.0.101.0/24", "10.0.102.0/24", "10.0.103.0/24"]
}

variable "cluster_api_access_cidrs" {
  description = "CIDRs allowed to access the EKS API server endpoint"
  type        = list(string)
  sensitive   = true
}

variable "rds_master_password" {
  description = "Master password for RDS Aurora"
  type        = string
  sensitive   = true
}

variable "rds_reader_count" {
  description = "Number of Aurora read replica instances"
  type        = number
  default     = 2
}

variable "redis_auth_token" {
  description = "Auth token for ElastiCache Redis"
  type        = string
  sensitive   = true
}

# ============================================================================
# Terraform — AWS Provider & Backend Configuration
# ============================================================================
terraform {
  required_version = ">= 1.7"
  required_providers {
    aws = {
      source  = "hashicorp/aws"
      version = "~> 5.40"
    }
    kubernetes = {
      source  = "hashicorp/kubernetes"
      version = "~> 2.28"
    }
    helm = {
      source  = "hashicorp/helm"
      version = "~> 2.13"
    }
  }

  # Remote state — S3 with DynamoDB locking
  backend "s3" {
    bucket         = "hr-voice-agent-terraform-state"
    key            = "aws/terraform.tfstate"
    region         = "ap-south-1"
    encrypt        = true
    kms_key_id     = "alias/terraform-state-key"
    dynamodb_table = "hr-voice-agent-terraform-lock"
  }
}

provider "aws" {
  region = var.aws_region
  default_tags {
    tags = {
      Project     = "hr-voice-agent"
      Environment = var.environment
      ManagedBy   = "terraform"
      CostCenter  = "platform-engineering"
    }
  }
}

# ── Data Sources ─────────────────────────────────────────────────────────────
data "aws_availability_zones" "available" {}

data "aws_caller_identity" "current" {}

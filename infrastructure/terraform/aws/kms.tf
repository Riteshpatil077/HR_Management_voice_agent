# ============================================================================
# Terraform — KMS Keys (one per data classification)
# ============================================================================

# EKS cluster secrets encryption key
resource "aws_kms_key" "eks" {
  description             = "EKS cluster secrets encryption — hr-voice-agent ${var.environment}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = false
}
resource "aws_kms_alias" "eks" {
  name          = "alias/hr-voice-agent-eks-${var.environment}"
  target_key_id = aws_kms_key.eks.key_id
}

# RDS Aurora encryption key
resource "aws_kms_key" "rds" {
  description             = "RDS Aurora encryption — hr-voice-agent ${var.environment}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = true
}
resource "aws_kms_alias" "rds" {
  name          = "alias/hr-voice-agent-rds-${var.environment}"
  target_key_id = aws_kms_key.rds.key_id
}

# ElastiCache encryption key
resource "aws_kms_key" "elasticache" {
  description             = "ElastiCache encryption — hr-voice-agent ${var.environment}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
}
resource "aws_kms_alias" "elasticache" {
  name          = "alias/hr-voice-agent-redis-${var.environment}"
  target_key_id = aws_kms_key.elasticache.key_id
}

# S3 data encryption key
resource "aws_kms_key" "s3" {
  description             = "S3 data encryption — hr-voice-agent ${var.environment}"
  deletion_window_in_days = 30
  enable_key_rotation     = true
  multi_region            = true
}
resource "aws_kms_alias" "s3" {
  name          = "alias/hr-voice-agent-s3-${var.environment}"
  target_key_id = aws_kms_key.s3.key_id
}

# ── S3 Buckets ────────────────────────────────────────────────────────────────

# Call recordings bucket
resource "aws_s3_bucket" "recordings" {
  bucket = "hr-voice-agent-recordings-${var.environment}-${data.aws_caller_identity.current.account_id}"
  
  lifecycle {
    prevent_destroy = true
  }
}

resource "aws_s3_bucket_versioning" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  versioning_configuration {
    status = "Enabled"
  }
}

resource "aws_s3_bucket_server_side_encryption_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
    bucket_key_enabled = true
  }
}

resource "aws_s3_bucket_public_access_block" "recordings" {
  bucket                  = aws_s3_bucket.recordings.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

# Lifecycle: move to Glacier after 90 days, delete after 2 years
resource "aws_s3_bucket_lifecycle_configuration" "recordings" {
  bucket = aws_s3_bucket.recordings.id
  rule {
    id     = "archive-old-recordings"
    status = "Enabled"
    filter {}
    transition {
      days          = 90
      storage_class = "GLACIER_IR"
    }
    expiration {
      days = 730
    }
  }
}

# ML model artifacts bucket
resource "aws_s3_bucket" "artifacts" {
  bucket = "hr-voice-agent-artifacts-${var.environment}-${data.aws_caller_identity.current.account_id}"
}

resource "aws_s3_bucket_server_side_encryption_configuration" "artifacts" {
  bucket = aws_s3_bucket.artifacts.id
  rule {
    apply_server_side_encryption_by_default {
      sse_algorithm     = "aws:kms"
      kms_master_key_id = aws_kms_key.s3.arn
    }
  }
}

resource "aws_s3_bucket_public_access_block" "artifacts" {
  bucket                  = aws_s3_bucket.artifacts.id
  block_public_acls       = true
  block_public_policy     = true
  ignore_public_acls      = true
  restrict_public_buckets = true
}

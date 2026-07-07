output "eks_cluster_name" {
  description = "EKS cluster name"
  value       = module.eks.cluster_name
}

output "eks_cluster_endpoint" {
  description = "EKS cluster API endpoint"
  value       = module.eks.cluster_endpoint
  sensitive   = true
}

output "eks_oidc_provider_arn" {
  description = "OIDC provider ARN for IRSA"
  value       = module.eks.oidc_provider_arn
}

output "rds_cluster_endpoint" {
  description = "Aurora write endpoint"
  value       = aws_rds_cluster.hrvoice.endpoint
  sensitive   = true
}

output "rds_reader_endpoint" {
  description = "Aurora read endpoint"
  value       = aws_rds_cluster.hrvoice.reader_endpoint
  sensitive   = true
}

output "redis_primary_endpoint" {
  description = "ElastiCache Redis primary endpoint"
  value       = aws_elasticache_replication_group.hrvoice.primary_endpoint_address
  sensitive   = true
}

output "s3_recordings_bucket" {
  description = "S3 bucket name for call recordings"
  value       = aws_s3_bucket.recordings.bucket
}

output "s3_artifacts_bucket" {
  description = "S3 bucket name for ML artifacts"
  value       = aws_s3_bucket.artifacts.bucket
}

output "kms_rds_key_arn" {
  description = "KMS key ARN for RDS"
  value       = aws_kms_key.rds.arn
}

output "kms_s3_key_arn" {
  description = "KMS key ARN for S3"
  value       = aws_kms_key.s3.arn
}

output "vpc_id" {
  description = "VPC ID"
  value       = module.vpc.vpc_id
}

output "private_subnet_ids" {
  description = "Private subnet IDs"
  value       = module.vpc.private_subnets
}

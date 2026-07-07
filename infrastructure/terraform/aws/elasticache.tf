# ============================================================================
# Terraform — Amazon ElastiCache (Redis 7) + S3 Buckets + KMS Keys
# ============================================================================

# ── ElastiCache Redis (Cluster Mode) ─────────────────────────────────────────
resource "aws_security_group" "redis" {
  name_prefix = "hr-voice-agent-redis-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    from_port       = 6379
    to_port         = 6380
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
}

resource "aws_elasticache_subnet_group" "hrvoice" {
  name       = "hr-voice-agent-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_elasticache_replication_group" "hrvoice" {
  replication_group_id       = "hr-voice-agent-${var.environment}"
  description                = "Redis cluster for HR Voice Agent"
  
  node_type                  = "cache.r7g.large"
  num_node_groups            = 3    # 3 shards
  replicas_per_node_group    = 2    # 2 read replicas per shard
  automatic_failover_enabled = true
  multi_az_enabled           = true
  
  engine_version             = "7.1"
  port                       = 6379
  
  subnet_group_name          = aws_elasticache_subnet_group.hrvoice.name
  security_group_ids         = [aws_security_group.redis.id]
  
  at_rest_encryption_enabled = true
  transit_encryption_enabled = true
  auth_token                 = var.redis_auth_token
  kms_key_id                 = aws_kms_key.elasticache.arn
  
  snapshot_retention_limit   = 7
  snapshot_window            = "04:00-05:00"
  
  maintenance_window         = "sun:05:00-sun:06:00"
  
  log_delivery_configuration {
    destination      = aws_cloudwatch_log_group.redis.name
    destination_type = "cloudwatch-logs"
    log_format       = "json"
    log_type         = "slow-log"
  }
}

resource "aws_cloudwatch_log_group" "redis" {
  name              = "/aws/elasticache/hr-voice-agent-${var.environment}"
  retention_in_days = 30
}

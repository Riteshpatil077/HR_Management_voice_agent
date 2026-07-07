# ============================================================================
# Terraform — Amazon RDS PostgreSQL (Aurora Serverless v2)
# Multi-AZ, encrypted, auto-scaling capacity, enhanced monitoring
# ============================================================================

resource "aws_db_subnet_group" "hrvoice" {
  name       = "hr-voice-agent-${var.environment}"
  subnet_ids = module.vpc.private_subnets
}

resource "aws_security_group" "rds" {
  name_prefix = "hr-voice-agent-rds-"
  vpc_id      = module.vpc.vpc_id

  ingress {
    description     = "PostgreSQL from EKS nodes"
    from_port       = 5432
    to_port         = 5432
    protocol        = "tcp"
    security_groups = [module.eks.node_security_group_id]
  }
  egress {
    from_port   = 0
    to_port     = 0
    protocol    = "-1"
    cidr_blocks = ["0.0.0.0/0"]
  }
}

resource "aws_rds_cluster" "hrvoice" {
  cluster_identifier     = "hr-voice-agent-${var.environment}"
  engine                 = "aurora-postgresql"
  engine_mode            = "provisioned"
  engine_version         = "16.2"
  database_name          = "hrvoice"
  master_username        = "hrvoice"
  master_password        = var.rds_master_password
  
  db_subnet_group_name   = aws_db_subnet_group.hrvoice.name
  vpc_security_group_ids = [aws_security_group.rds.id]
  
  # Encryption
  storage_encrypted = true
  kms_key_id        = aws_kms_key.rds.arn
  
  # Backup
  backup_retention_period   = 30
  preferred_backup_window   = "03:00-04:00"
  deletion_protection       = true
  skip_final_snapshot       = false
  final_snapshot_identifier = "hr-voice-agent-final-${var.environment}"
  
  # Serverless v2 scaling configuration
  serverlessv2_scaling_configuration {
    max_capacity = 64.0
    min_capacity = 0.5
  }

  enabled_cloudwatch_logs_exports = ["postgresql"]
  
  tags = {
    Name = "hr-voice-agent-aurora-${var.environment}"
  }
}

# Read replica instances
resource "aws_rds_cluster_instance" "writer" {
  count              = 1
  identifier         = "hr-voice-agent-writer-${count.index}"
  cluster_identifier = aws_rds_cluster.hrvoice.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.hrvoice.engine
  engine_version     = aws_rds_cluster.hrvoice.engine_version
  
  performance_insights_enabled          = true
  performance_insights_kms_key_id       = aws_kms_key.rds.arn
  performance_insights_retention_period = 7
  monitoring_interval                   = 60
  monitoring_role_arn                   = aws_iam_role.rds_monitoring.arn
}

resource "aws_rds_cluster_instance" "readers" {
  count              = var.rds_reader_count
  identifier         = "hr-voice-agent-reader-${count.index}"
  cluster_identifier = aws_rds_cluster.hrvoice.id
  instance_class     = "db.serverless"
  engine             = aws_rds_cluster.hrvoice.engine
  engine_version     = aws_rds_cluster.hrvoice.engine_version
  
  performance_insights_enabled = true
  monitoring_interval          = 60
  monitoring_role_arn          = aws_iam_role.rds_monitoring.arn
}

# Enhanced monitoring role
resource "aws_iam_role" "rds_monitoring" {
  name = "hr-voice-agent-rds-monitoring-${var.environment}"
  assume_role_policy = jsonencode({
    Version = "2012-10-17"
    Statement = [
      {
        Action = "sts:AssumeRole"
        Effect = "Allow"
        Principal = {
          Service = "monitoring.rds.amazonaws.com"
        }
      }
    ]
  })
}

resource "aws_iam_role_policy_attachment" "rds_monitoring" {
  role       = aws_iam_role.rds_monitoring.name
  policy_arn = "arn:aws:iam::aws:policy/service-role/AmazonRDSEnhancedMonitoringRole"
}
